/* Win32 sampling adapted from the received monitor. Identity and missing-data
 * handling replace its name grouping, PID-only cache and fabricated zeroes. */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <tlhelp32.h>
#include <psapi.h>
#include "pm.h"
#include "pm_json.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <locale.h>
#include <io.h>
#include <fcntl.h>

#define MAX_PROCESSES 10000
#define PAGE_ROWS 25
#define MAX_SELECTED 100
typedef struct {
    DWORD pid;
    uint64_t created, ticks;
    int64_t sampled_mono;
    double cpu, memory;
    bool identity, cpu_valid, memory_valid, times_valid;
    char name[1041];
} Process;
typedef struct {DWORD pid;uint64_t created;HANDLE handle;} Selected;
typedef struct {
    CRITICAL_SECTION lock;
    volatile LONG stop;
    Selected selected[MAX_SELECTED];
    Process *previous, *current;
    size_t previous_count;
    unsigned processors, interval;
    uint64_t previous_idle, previous_total, snapshot_id, send_failures;
    bool system_baseline;
    SOCKET socket;
    struct sockaddr_in destination;
} Monitor;
static Monitor *console_monitor;
static BOOL WINAPI interrupted(DWORD code) {
    (void)code;
    if(console_monitor)InterlockedExchange(&console_monitor->stop,1);
    return TRUE;
}
static uint64_t ticks(FILETIME ft) {
    ULARGE_INTEGER t;t.LowPart=ft.dwLowDateTime;t.HighPart=ft.dwHighDateTime;
    return t.QuadPart;
}
static int compare_pid(const void *a,const void *b) {
    DWORD x=((const Process*)a)->pid,y=((const Process*)b)->pid;
    return (x>y)-(x<y);
}
static bool identity(const cJSON *a,DWORD *pid,uint64_t *created,HANDLE *handle) {
    int64_t p;char *end=NULL;const char *text=pm_text(a,"created");
    if(!pm_integer(a,"pid",1,UINT32_MAX,&p)||!*text)return false;
    for(const char *c=text;*c;c++)if(*c<'0'||*c>'9')return false;
    *created=strtoull(text,&end,10);*pid=(DWORD)p;
    if(!*created||*end)return false;
    HANDLE h=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,*pid);
    if(!h)return false;
    FILETIME ct,et,kt,ut;
    if(WaitForSingleObject(h,0)!=WAIT_TIMEOUT||!GetProcessTimes(h,&ct,&et,&kt,&ut)||ticks(ct)!=*created){CloseHandle(h);return false;}
    *handle=h;return true;
}
static DWORD WINAPI controls(LPVOID arg) {
    Monitor *m=arg;
    char *line=malloc(PM_COMMAND);if(!line){InterlockedExchange(&m->stop,1);return 1;}
    size_t length=0;bool overflow=false;int ch;
    while((ch=fgetc(stdin))!=EOF) {
        if(ch!='\n'){if(ch==0)overflow=true;if(length<PM_COMMAND-1)line[length++]=(char)ch;else overflow=true;continue;}
        line[length]=0;length=0;cJSON *r=overflow?NULL:pm_json_parse(line);overflow=false;
        const char *op=pm_text(r,"op");bool ok=false;const char *message="invalid command";
        if(!cJSON_IsObject(r)||pm_number(r,"v",0)!=1||!*pm_text(r,"id")){pm_reply(r,false,message,NULL);cJSON_Delete(r);continue;}
        if(!strcmp(op,"stop")){pm_reply(r,true,"stopping",NULL);cJSON_Delete(r);break;}
        EnterCriticalSection(&m->lock);
        cJSON *args=cJSON_GetObjectItemCaseSensitive(r,"args");
        if(!strcmp(op,"validate")||!strcmp(op,"track")) {
            DWORD pid;uint64_t created;HANDLE handle=NULL;
            ok=identity(args,&pid,&created,&handle);message="identity unavailable, ended or capacity reached";
            if(ok&&!strcmp(op,"track")) {
                int slot=-1;
                for(int i=0;i<MAX_SELECTED;i++) {
                    if(m->selected[i].handle&&m->selected[i].pid==pid&&m->selected[i].created==created){slot=i;break;}
                    if(!m->selected[i].handle&&slot<0)slot=i;
                }
                if(slot<0)ok=false;
                else {if(m->selected[slot].handle)CloseHandle(m->selected[slot].handle);m->selected[slot]=(Selected){pid,created,handle};handle=NULL;}
            }
            if(handle)CloseHandle(handle);
        } else if(!strcmp(op,"untrack")) {
            const char *key=pm_text(args,"source");ok=pm_identifier(key,64)&&!strncmp(key,"p.",2);
            for(int i=0;i<MAX_SELECTED;i++)if(m->selected[i].handle) {
                char source[65];snprintf(source,sizeof(source),"p.%lu.%llu",m->selected[i].pid,(unsigned long long)m->selected[i].created);
                if(!strcmp(key,source)){CloseHandle(m->selected[i].handle);memset(&m->selected[i],0,sizeof(Selected));}
            }
        } else if(!strcmp(op,"status"))ok=true;
        LeaveCriticalSection(&m->lock);
        pm_reply(r,ok,ok?"applied":message,NULL);cJSON_Delete(r);
    }
    free(line);InterlockedExchange(&m->stop,1);return 0;
}
static void send_metric(Monitor *m,const char *source,const char *name,double value) {
    char line[PM_LINE+1];int n=snprintf(line,sizeof(line),"%s/%s:%.12g|g",source,name,value);
    if(n<=0||n>PM_LINE||sendto(m->socket,line,n,0,(struct sockaddr*)&m->destination,sizeof(m->destination))!=n)m->send_failures++;
}
static void number_or_null(cJSON *o,const char *key,double value,bool valid) {
    cJSON_AddItemToObject(o,key,valid?cJSON_CreateNumber(value):cJSON_CreateNull());
}
static cJSON *system_sample(Monitor *m) {
    cJSON *o=cJSON_CreateObject();FILETIME idle,kernel,user;
    bool valid=false;double cpu=0;
    if(GetActiveProcessorGroupCount()==1&&GetSystemTimes(&idle,&kernel,&user)) {
        uint64_t i=ticks(idle),total=ticks(kernel)+ticks(user);
        if(m->system_baseline&&total>m->previous_total&&i>=m->previous_idle&&i-m->previous_idle<=total-m->previous_total){cpu=100.0*(1.0-(double)(i-m->previous_idle)/(double)(total-m->previous_total));valid=true;}
        m->previous_idle=i;m->previous_total=total;m->system_baseline=true;
    } else m->system_baseline=false;
    number_or_null(o,"cpu_percent",cpu,valid);
    if(valid)send_metric(m,"system","cpu.percent",cpu);
    MEMORYSTATUSEX ram={0};ram.dwLength=sizeof(ram);bool memory=GlobalMemoryStatusEx(&ram)!=0;
    double used=(double)(ram.ullTotalPhys-ram.ullAvailPhys),percent=ram.ullTotalPhys?used*100.0/(double)ram.ullTotalPhys:0;
    number_or_null(o,"memory_used_bytes",used,memory);
    number_or_null(o,"memory_total_bytes",(double)ram.ullTotalPhys,memory);
    number_or_null(o,"memory_percent",percent,memory&&ram.ullTotalPhys>0);
    if(memory&&ram.ullTotalPhys) {
        send_metric(m,"system","memory.used",used);send_metric(m,"system","memory.total",(double)ram.ullTotalPhys);
        send_metric(m,"system","memory.available",(double)ram.ullAvailPhys);send_metric(m,"system","memory.percent",percent);
    }
    cJSON_AddNumberToObject(o,"logical_processors",m->processors);
    cJSON_AddBoolToObject(o,"cpu_topology_supported",GetActiveProcessorGroupCount()==1);
    return o;
}
static void read_process(Monitor *m,Process *p,const PROCESSENTRY32W *entry) {
    memset(p,0,sizeof(*p));p->pid=entry->th32ProcessID;
    if(!WideCharToMultiByte(CP_UTF8,0,entry->szExeFile,-1,p->name,sizeof(p->name),NULL,NULL))strcpy(p->name,"Unavailable name");
    HANDLE h=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,p->pid);
    FILETIME ct,et,kt,ut;
    if(h) {
        if(GetProcessTimes(h,&ct,&et,&kt,&ut)) {
            p->created=ticks(ct);p->identity=true;p->times_valid=true;
            p->ticks=ticks(kt)+ticks(ut);p->sampled_mono=pm_mono_us();
            Process *old=bsearch(p,m->previous,m->previous_count,sizeof(Process),compare_pid);
            if(old&&old->times_valid&&old->created==p->created&&p->ticks>=old->ticks&&p->sampled_mono>old->sampled_mono&&m->processors&&GetActiveProcessorGroupCount()==1) {
                p->cpu=100.0*(double)(p->ticks-old->ticks)/(10.0*(double)(p->sampled_mono-old->sampled_mono)*m->processors);
                p->cpu_valid=p->cpu>=0&&p->cpu<=100;
            }
        }
        CloseHandle(h);
    }
    h=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,p->pid);
    if(h) {
        PROCESS_MEMORY_COUNTERS ram={0};
        /* Reopening for memory must still refer to the same process instance. */
        if(p->identity&&GetProcessTimes(h,&ct,&et,&kt,&ut)&&ticks(ct)==p->created&&GetProcessMemoryInfo(h,&ram,sizeof(ram))){p->memory=(double)ram.WorkingSetSize;p->memory_valid=true;}
        CloseHandle(h);
    }
}
static bool is_selected(Monitor *m,const Process *p) {
    for(int i=0;i<MAX_SELECTED;i++)if(m->selected[i].handle&&m->selected[i].pid==p->pid&&m->selected[i].created==p->created)return true;
    return false;
}
static void sample(Monitor *m) {
    EnterCriticalSection(&m->lock);
    unsigned processors=GetActiveProcessorCount(ALL_PROCESSOR_GROUPS);
    if(processors!=m->processors){m->previous_count=0;m->system_baseline=false;m->processors=processors;}
    int64_t sampled_at=pm_wall_us();cJSON *system=system_sample(m);
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    size_t count=0;bool complete=snapshot!=INVALID_HANDLE_VALUE,truncated=false;
    if(complete) {
        PROCESSENTRY32W entry={0};entry.dwSize=sizeof(entry);
        if(Process32FirstW(snapshot,&entry))do {
            if(count==MAX_PROCESSES){truncated=true;break;}
            read_process(m,&m->current[count++],&entry);
        } while(Process32NextW(snapshot,&entry));
        else complete=false;
        CloseHandle(snapshot);
    }
    for(int i=0;i<MAX_SELECTED;i++)if(m->selected[i].handle&&WaitForSingleObject(m->selected[i].handle,0)==WAIT_OBJECT_0) {
        char key[65];snprintf(key,sizeof(key),"p.%lu.%llu",m->selected[i].pid,(unsigned long long)m->selected[i].created);
        cJSON *ended=cJSON_CreateObject();cJSON_AddStringToObject(ended,"event","ended");cJSON_AddStringToObject(ended,"source",key);pm_emit(ended);
        CloseHandle(m->selected[i].handle);memset(&m->selected[i],0,sizeof(Selected));
    }
    m->snapshot_id++;size_t pages=count?(count+PAGE_ROWS-1)/PAGE_ROWS:1;
    for(size_t page=0;page<pages;page++) {
        cJSON *event=cJSON_CreateObject(),*rows=cJSON_CreateArray();
        cJSON_AddStringToObject(event,"event","snapshot");cJSON_AddNumberToObject(event,"snapshot_id",(double)m->snapshot_id);
        cJSON_AddNumberToObject(event,"page",(double)page);cJSON_AddNumberToObject(event,"pages",(double)pages);
        cJSON_AddNumberToObject(event,"sampled_at_us",(double)sampled_at);cJSON_AddNumberToObject(event,"send_failures",(double)m->send_failures);
        cJSON_AddBoolToObject(event,"complete",complete);cJSON_AddBoolToObject(event,"truncated",truncated);
        if(page==0){cJSON_AddItemToObject(event,"system",system);system=NULL;}
        for(size_t j=page*PAGE_ROWS;j<count&&j<(page+1)*PAGE_ROWS;j++) {
            Process *p=&m->current[j];cJSON *row=cJSON_CreateObject();char created[32],key[65];
            snprintf(created,sizeof(created),"%llu",(unsigned long long)p->created);snprintf(key,sizeof(key),"p.%lu.%s",p->pid,created);
            bool selected=p->identity&&is_selected(m,p);
            cJSON_AddNumberToObject(row,"pid",p->pid);cJSON_AddStringToObject(row,"created",p->identity?created:"");
            cJSON_AddStringToObject(row,"source",p->identity?key:"");cJSON_AddStringToObject(row,"name",p->name);
            cJSON_AddStringToObject(row,"state",!p->identity?"unavailable":!p->cpu_valid?"warming_up":"accessible");
            cJSON_AddBoolToObject(row,"tracked",selected);
            number_or_null(row,"cpu_percent",p->cpu,p->cpu_valid);number_or_null(row,"memory_bytes",p->memory,p->memory_valid);
            cJSON_AddItemToArray(rows,row);
            if(selected){if(p->cpu_valid)send_metric(m,key,"cpu.percent",p->cpu);if(p->memory_valid)send_metric(m,key,"memory.working_set",p->memory);}
        }
        cJSON_AddItemToObject(event,"processes",rows);pm_emit(event);
    }
    cJSON_Delete(system);
    qsort(m->current,count,sizeof(Process),compare_pid);
    Process *swap=m->previous;m->previous=m->current;m->current=swap;m->previous_count=count;
    LeaveCriticalSection(&m->lock);
}
int main(int argc,char **argv) {
    if(argc!=5||strcmp(argv[1],"--port")||strcmp(argv[3],"--sample")){fprintf(stderr,"usage: pulsemonitor --port PORT --sample SECONDS\n");return 2;}
    char *end=NULL;long port=strtol(argv[2],&end,10);if(*end||port<1024||port>65535)return 2;
    long interval=strtol(argv[4],&end,10);if(*end||interval<1||interval>60)return 2;
    setlocale(LC_NUMERIC,"C");_setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);pm_output_init();
    Monitor *m=calloc(1,sizeof(*m));if(!m)return 2;
    m->previous=calloc(MAX_PROCESSES,sizeof(Process));m->current=calloc(MAX_PROCESSES,sizeof(Process));
    if(!m->previous||!m->current){free(m->previous);free(m->current);free(m);return 2;}
    InitializeCriticalSection(&m->lock);m->interval=(unsigned)interval;
    WSADATA ws;if(WSAStartup(MAKEWORD(2,2),&ws)){free(m->previous);free(m->current);DeleteCriticalSection(&m->lock);free(m);return 2;}
    m->socket=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);
    if(m->socket==INVALID_SOCKET){WSACleanup();free(m->previous);free(m->current);DeleteCriticalSection(&m->lock);free(m);return 2;}
    m->destination.sin_family=AF_INET;m->destination.sin_port=htons((u_short)port);m->destination.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    HANDLE input=CreateThread(NULL,0,controls,m,0,NULL);
    if(!input){closesocket(m->socket);WSACleanup();free(m->previous);free(m->current);DeleteCriticalSection(&m->lock);free(m);return 2;}
    console_monitor=m;SetConsoleCtrlHandler(interrupted,TRUE);
    cJSON *ready=cJSON_CreateObject();cJSON_AddStringToObject(ready,"event","ready");cJSON_AddStringToObject(ready,"component","monitor");pm_emit(ready);
    int64_t next=pm_mono_us();
    while(!m->stop) {
        if(pm_mono_us()>=next){sample(m);next=pm_mono_us()+(int64_t)m->interval*1000000;}
        Sleep(20);
    }
    CancelSynchronousIo(input);WaitForSingleObject(input,INFINITE);CloseHandle(input);
    for(int i=0;i<MAX_SELECTED;i++)if(m->selected[i].handle)CloseHandle(m->selected[i].handle);
    closesocket(m->socket);WSACleanup();SetConsoleCtrlHandler(interrupted,FALSE);console_monitor=NULL;
    cJSON *done=cJSON_CreateObject();cJSON_AddStringToObject(done,"event","stopped");cJSON_AddBoolToObject(done,"clean",true);pm_emit(done);
    DeleteCriticalSection(&m->lock);free(m->previous);free(m->current);free(m);return 0;
}
