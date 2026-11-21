#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include "pm_db.h"
#include <io.h>
#include <fcntl.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define TASKS 128
typedef struct {int slot;cJSON *command;} Task;
typedef struct {
    CRITICAL_SECTION lock;
    HANDLE available;
    volatile LONG stop, abort_writer, finish_writer;
    PmDb db;PmStore store;PmHealth health;
    PmBatch batches[PM_PENDING];PmHealth batch_health[PM_PENDING];bool occupied[PM_PENDING];
    Task tasks[TASKS];int head,tail,tasks_count,inflight;
    int64_t wall_anchor,mono_anchor,start,sequence,frozen_end;
    int window,port;bool frozen,storage_failed;
    char last_error[256];
} Engine;
static Engine *console_engine;
static int64_t now_us(Engine *e){return e->wall_anchor+pm_mono_us()-e->mono_anchor;}
static BOOL WINAPI interrupted(DWORD type){(void)type;if(console_engine)InterlockedExchange(&console_engine->stop,1);return TRUE;}
static uint64_t active_samples(Engine *e){uint64_t n=0;for(size_t i=0;i<PM_SERIES;i++)n+=e->store.series[i].stats.count;return n;}
static uint64_t pending_samples(Engine *e){uint64_t n=active_samples(e);for(int i=0;i<PM_PENDING;i++)if(e->occupied[i])for(size_t j=0;j<e->batches[i].count;j++)n+=e->batches[i].rows[j].stats.count;return n;}
static cJSON *status(Engine *e) {
    cJSON *o=cJSON_CreateObject();EnterCriticalSection(&e->lock);
    cJSON_AddNumberToObject(o,"datagrams_received",(double)e->health.datagrams);
    cJSON_AddNumberToObject(o,"datagrams_rejected",(double)e->health.bad_datagrams);
    cJSON_AddNumberToObject(o,"lines_received",(double)e->health.lines);
    cJSON_AddNumberToObject(o,"accepted",(double)e->health.accepted);cJSON_AddNumberToObject(o,"rejected",(double)e->health.rejected);
    cJSON_AddNumberToObject(o,"known_dropped",(double)e->health.dropped);cJSON_AddNumberToObject(o,"write_failures",(double)e->health.write_failures);
    cJSON_AddNumberToObject(o,"pending_batches",e->health.pending);cJSON_AddNumberToObject(o,"inflight_batches",e->inflight>=0?1:0);
    cJSON_AddNumberToObject(o,"queued_batches",e->health.pending-(e->inflight>=0?1:0));
    cJSON_AddNumberToObject(o,"uncommitted_samples",(double)pending_samples(e));
    cJSON_AddNumberToObject(o,"active_samples",(double)active_samples(e));
    cJSON_AddNumberToObject(o,"last_received_us",(double)e->health.last_received);cJSON_AddNumberToObject(o,"last_commit_us",(double)e->health.last_commit);
    cJSON_AddNumberToObject(o,"heartbeat_us",(double)now_us(e));
    cJSON_AddBoolToObject(o,"clock_warning",e->health.clock_warning);cJSON_AddBoolToObject(o,"backpressure",e->frozen);
    cJSON_AddBoolToObject(o,"write_healthy",!e->storage_failed);cJSON_AddStringToObject(o,"last_error",e->last_error);
    cJSON_AddStringToObject(o,"state",e->stop?"stopping":"running");
    LeaveCriticalSection(&e->lock);return o;
}
static bool enqueue(Engine *e,Task task) {
    if(e->tasks_count>=TASKS)return false;
    e->tasks[e->tail]=task;e->tail=(e->tail+1)%TASKS;e->tasks_count++;SetEvent(e->available);return true;
}
static bool verified_process(const cJSON *req) {
    cJSON *a=cJSON_GetObjectItemCaseSensitive(req,"args");int64_t pid=0;
    if(!pm_integer(a,"pid",1,UINT32_MAX,&pid))return false;
    char *end=NULL;const char *value=pm_text(a,"created");unsigned long long expected=strtoull(value,&end,10);
    if(!*value||!end||*end||!expected)return false;
    HANDLE h=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,(DWORD)pid);if(!h)return false;
    FILETIME ct={0},et,kt,ut;ULARGE_INTEGER c;DWORD exit_code=0;
    bool ok=GetProcessTimes(h,&ct,&et,&kt,&ut)&&GetExitCodeProcess(h,&exit_code)&&exit_code==STILL_ACTIVE;
    c.LowPart=ct.dwLowDateTime;c.HighPart=ct.dwHighDateTime;CloseHandle(h);return ok&&c.QuadPart==expected;
}
static DWORD WINAPI input_thread(LPVOID arg) {
    Engine *e=arg;char *line=malloc(PM_COMMAND);if(!line){InterlockedExchange(&e->stop,1);return 1;}
    size_t n=0;bool overflow=false;int ch;
    while((ch=fgetc(stdin))!=EOF) {
        if(ch!='\n'){if(ch==0)overflow=true;if(n<PM_COMMAND-1)line[n++]=(char)ch;else overflow=true;continue;}
        line[n]=0;n=0;cJSON *req=overflow?NULL:pm_json_parse(line);overflow=false;
        if(!cJSON_IsObject(req)||pm_number(req,"v",0)!=1||!*pm_text(req,"id")) {pm_reply(req,false,"invalid bounded JSON command",NULL);cJSON_Delete(req);continue;}
        const char *op=pm_text(req,"op");
        if(!strcmp(op,"status")){pm_reply(req,true,"",status(e));cJSON_Delete(req);continue;}
        if(!strcmp(op,"stop")){pm_reply(req,true,"stopping; await stopped event",NULL);cJSON_Delete(req);InterlockedExchange(&e->stop,1);break;}
        bool track=!strcmp(op,"track");
        if(track&&!verified_process(req)){pm_reply(req,false,"process identity unavailable or ended",NULL);cJSON_Delete(req);continue;}
        EnterCriticalSection(&e->lock);
        bool ok=!e->stop&&e->tasks_count<TASKS-PM_PENDING&&enqueue(e,(Task){-1,req});
        LeaveCriticalSection(&e->lock);
        if(!ok){pm_reply(req,false,"busy or stopping",NULL);cJSON_Delete(req);}
    }
    free(line);InterlockedExchange(&e->stop,1);return 0;
}
static DWORD WINAPI writer_thread(LPVOID arg) {
    Engine *e=arg;
    for(;;) {
        EnterCriticalSection(&e->lock);
        if(!e->tasks_count){bool done=e->finish_writer||e->abort_writer;ResetEvent(e->available);LeaveCriticalSection(&e->lock);if(done)break;WaitForSingleObject(e->available,100);continue;}
        Task task=e->tasks[e->head];e->head=(e->head+1)%TASKS;e->tasks_count--;
        if(task.slot>=0)e->inflight=task.slot;
        LeaveCriticalSection(&e->lock);
        if(task.command) {
            EnterCriticalSection(&e->lock);e->db.error[0]=0;
            bool ok=!e->abort_writer&&pm_db_command(&e->db,&e->store,task.command,now_us(e));
            char err[256];snprintf(err,sizeof(err),"%s",e->db.error);
            LeaveCriticalSection(&e->lock);
            pm_reply(task.command,ok,ok?"applied":err,NULL);cJSON_Delete(task.command);
        } else {
            unsigned delay=50;bool committed=false;
            while(!e->abort_writer) {
                if(pm_db_batch(&e->db,&e->batches[task.slot],&e->batch_health[task.slot])){committed=true;break;}
                EnterCriticalSection(&e->lock);e->storage_failed=true;e->health.write_failures++;
                snprintf(e->last_error,sizeof(e->last_error),"%s",e->db.error);LeaveCriticalSection(&e->lock);
                Sleep(delay);if(delay<500)delay*=2;
            }
            EnterCriticalSection(&e->lock);
            if(committed){e->occupied[task.slot]=false;e->health.pending--;e->health.last_commit=now_us(e);e->storage_failed=false;e->last_error[0]=0;}
            e->inflight=-1;LeaveCriticalSection(&e->lock);
            if(!committed)break;
            EnterCriticalSection(&e->lock);
            e->db.clock_warning=e->health.clock_warning;
            LeaveCriticalSection(&e->lock);
            pm_db_retention(&e->db,now_us(e));
        }
    }
    return 0;
}
static bool rotate(Engine *e,bool partial) {
    EnterCriticalSection(&e->lock);int64_t now=now_us(e);
    if(!e->frozen && !partial && now-e->start<(int64_t)e->window*1000000){LeaveCriticalSection(&e->lock);return true;}
    if(!e->frozen){e->frozen_end=now>e->start?now:e->start+1;e->frozen=true;}
    int slot=-1;for(int i=0;i<PM_PENDING;i++)if(!e->occupied[i]){slot=i;break;}
    if(slot<0||e->tasks_count>=TASKS){LeaveCriticalSection(&e->lock);return false;}
    PmBatch *b=&e->batches[slot];b->sequence=e->sequence++;b->start_us=e->start;b->end_us=e->frozen_end;b->partial=partial;
    pm_snapshot(&e->store,b);e->occupied[slot]=true;e->health.pending++;
    e->batch_health[slot]=e->health;enqueue(e,(Task){slot,NULL});
    e->start=now;e->frozen=false;LeaveCriticalSection(&e->lock);return true;
}
static void packet(Engine *e,const char *data,int length) {
    EnterCriticalSection(&e->lock);e->health.datagrams++;e->health.last_received=now_us(e);
    int lines=1;for(int i=0;i<length;i++)if(data[i]=='\n'&&i<length-1)lines++;
    if(length<=0||length>PM_PACKET||lines>16){e->health.bad_datagrams++;LeaveCriticalSection(&e->lock);return;}
    int begin=0;
    for(int i=0;i<=length;i++)if(i==length||data[i]=='\n') {
        if(i==length&&begin==length)break;
        e->health.lines++;
        if(e->frozen)e->health.dropped++;
        else {PmInput in;if(pm_parse(data+begin,(size_t)(i-begin),&in)&&pm_update(&e->store,&in,e->health.last_received))e->health.accepted++;else e->health.rejected++;}
        begin=i+1;
    }
    LeaveCriticalSection(&e->lock);
}
static cJSON *read_config(const char *path) {
    FILE *f=fopen(path,"rb");if(!f)return NULL;
    char *s=calloc(PM_COMMAND,1);if(!s){fclose(f);return NULL;}
    size_t n=fread(s,1,PM_COMMAND-1,f);bool too_long=fgetc(f)!=EOF;fclose(f);
    cJSON *o=too_long||!n||memchr(s,0,n)?NULL:pm_json_parse(s);free(s);return o;
}
int main(int argc,char **argv) {
    setlocale(LC_NUMERIC,"C");_setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);pm_output_init();
    const char *config_path=NULL,*session=NULL;
    for(int i=1;i+1<argc;i+=2){if(!strcmp(argv[i],"--config"))config_path=argv[i+1];else if(!strcmp(argv[i],"--session"))session=argv[i+1];else return 2;}
    if(!config_path||!session){fprintf(stderr,"usage: pulsecollector --config absolute.json --session UUID\n");return 2;}
    cJSON *config=read_config(config_path);int64_t sample,window,port,retention;
    if(!config||!pm_integer(config,"sample_seconds",1,60,&sample)||!pm_integer(config,"window_seconds",sample,60,&window)||!pm_integer(config,"udp_port",1024,65535,&port)||!pm_integer(config,"retention_days",1,30,&retention)||!*pm_text(config,"database")){fprintf(stderr,"invalid collector configuration\n");cJSON_Delete(config);return 2;}
    Engine *e=calloc(1,sizeof(*e));if(!e)return 2;
    e->mono_anchor=pm_mono_us();e->wall_anchor=pm_wall_us();e->start=e->wall_anchor;e->window=(int)window;e->port=(int)port;e->inflight=-1;
    InitializeCriticalSection(&e->lock);e->available=CreateEvent(NULL,TRUE,FALSE,NULL);
    if(!e->available||!pm_db_open(&e->db,pm_text(config,"database"),session,e->wall_anchor,(int)sample,(int)window,(int)retention)||!pm_db_seed(&e->db,&e->store,config,e->wall_anchor)){fprintf(stderr,"collector startup: %s\n",e->db.error);pm_db_close(&e->db);if(e->available)CloseHandle(e->available);DeleteCriticalSection(&e->lock);free(e);cJSON_Delete(config);return 2;}
    cJSON_Delete(config);e->health.clock_warning=e->db.clock_warning;
    WSADATA ws;SOCKET sock=INVALID_SOCKET;
    if(WSAStartup(MAKEWORD(2,2),&ws)==0)sock=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);
    struct sockaddr_in address={0};address.sin_family=AF_INET;address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);address.sin_port=htons((u_short)port);
    BOOL exclusive=TRUE;if(sock!=INVALID_SOCKET)setsockopt(sock,SOL_SOCKET,SO_EXCLUSIVEADDRUSE,(const char*)&exclusive,sizeof(exclusive));
    if(sock==INVALID_SOCKET||bind(sock,(struct sockaddr*)&address,sizeof(address))==SOCKET_ERROR){fprintf(stderr,"cannot bind loopback UDP port %lld: %d\n",port,WSAGetLastError());if(sock!=INVALID_SOCKET)closesocket(sock);WSACleanup();pm_db_close(&e->db);CloseHandle(e->available);DeleteCriticalSection(&e->lock);free(e);return 2;}
    u_long nonblocking=1;ioctlsocket(sock,FIONBIO,&nonblocking);
    console_engine=e;SetConsoleCtrlHandler(interrupted,TRUE);
    HANDLE writer=CreateThread(NULL,0,writer_thread,e,0,NULL),input=CreateThread(NULL,0,input_thread,e,0,NULL);
    if(!writer||!input){InterlockedExchange(&e->stop,1);InterlockedExchange(&e->abort_writer,1);}
    cJSON *ready=cJSON_CreateObject();cJSON_AddStringToObject(ready,"event","ready");cJSON_AddStringToObject(ready,"component","collector");cJSON_AddStringToObject(ready,"session",session);cJSON_AddNumberToObject(ready,"schema_version",1);cJSON_AddBoolToObject(ready,"clock_warning",e->health.clock_warning);if(writer&&input)pm_emit(ready);else cJSON_Delete(ready);
    while(!e->stop) {
        rotate(e,false);
        for(int i=0;i<64&&!e->stop;i++) {
            char data[PM_PACKET+1];int n=recv(sock,data,sizeof(data),0);
            if(n==SOCKET_ERROR){int err=WSAGetLastError();if(err==WSAEMSGSIZE){packet(e,data,PM_PACKET+1);continue;}if(err!=WSAEWOULDBLOCK)InterlockedExchange(&e->stop,1);break;}
            rotate(e,false);packet(e,data,n);
        }
        EnterCriticalSection(&e->lock);if(llabs(pm_wall_us()-now_us(e))>1000000)e->health.clock_warning=true;LeaveCriticalSection(&e->lock);Sleep(10);
    }
    closesocket(sock);int64_t deadline=pm_mono_us()+10000000;bool final_queued=false;
    while(pm_mono_us()<deadline) {
        if(!final_queued)final_queued=rotate(e,true);
        EnterCriticalSection(&e->lock);bool drained=final_queued&&e->health.pending==0&&e->tasks_count==0&&e->inflight<0;LeaveCriticalSection(&e->lock);
        if(drained)break;
        Sleep(20);
    }
    EnterCriticalSection(&e->lock);bool clean=final_queued&&e->health.pending==0&&e->tasks_count==0&&e->inflight<0;LeaveCriticalSection(&e->lock);
    InterlockedExchange(&e->finish_writer,1);if(!clean)InterlockedExchange(&e->abort_writer,1);SetEvent(e->available);
    if(writer){WaitForSingleObject(writer,INFINITE);CloseHandle(writer);}
    if(input){CancelSynchronousIo(input);WaitForSingleObject(input,INFINITE);CloseHandle(input);}
    clean=pm_db_finish(&e->db,now_us(e),clean)&&clean;
    cJSON *done=status(e);cJSON_AddStringToObject(done,"event","stopped");cJSON_AddBoolToObject(done,"clean",clean);pm_emit(done);
    for(int i=0;i<e->tasks_count;i++)cJSON_Delete(e->tasks[(e->head+i)%TASKS].command);
    pm_db_close(&e->db);WSACleanup();SetConsoleCtrlHandler(interrupted,FALSE);console_engine=NULL;
    CloseHandle(e->available);DeleteCriticalSection(&e->lock);free(e);return clean?0:1;
}
