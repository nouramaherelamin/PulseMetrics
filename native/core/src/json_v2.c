#include "pm.h"
#include "pm_json.h"
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static CRITICAL_SECTION output_lock;
const char *pm_text(const cJSON *o,const char *key) {
    const cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);
    return cJSON_IsString(v) && v->valuestring ? v->valuestring : "";
}
double pm_number(const cJSON *o,const char *key,double fallback) {
    const cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);
    return cJSON_IsNumber(v) && isfinite(v->valuedouble) ? v->valuedouble : fallback;
}
bool pm_integer(const cJSON *o,const char *key,int64_t min,int64_t max,int64_t *out) {
    double v=pm_number(o,key,NAN);
    if (!isfinite(v)||v<min||v>max||floor(v)!=v) return false;
    *out=(int64_t)v;return true;
}
static bool valid_tree(const cJSON *v) {
    for (;v;v=v->next) {
        if (cJSON_IsNumber(v) && !isfinite(v->valuedouble)) return false;
        if (cJSON_IsObject(v)) {
            for (cJSON *a=v->child;a;a=a->next)
                for(cJSON *b=a->next;b;b=b->next) if(a->string&&b->string&&!strcmp(a->string,b->string)) return false;
        }
        if (v->child&&!valid_tree(v->child)) return false;
    }
    return true;
}
cJSON *pm_json_parse(const char *s) {
    if (!s||strlen(s)>=PM_COMMAND) return NULL;
    cJSON *v=cJSON_Parse(s);
    if (!v||!valid_tree(v)) {cJSON_Delete(v);return NULL;}return v;
}
typedef struct {char *s;size_t n;bool failed;} Output;
static void put(Output *o,char c) {if(o->n>=PM_COMMAND-2)o->failed=true;else o->s[o->n++]=c;}
static void text(Output *o,const char *s) {while(*s)put(o,*s++);}
static void quoted(Output *o,const char *s) {
    put(o,'"');
    for (const unsigned char *p=(const unsigned char *)(s?s:"");*p;p++) {
        if (*p=='"'||*p=='\\') {put(o,'\\');put(o,(char)*p);}
        else if(*p<32) {char b[7];snprintf(b,sizeof(b),"\\u%04x",*p);text(o,b);}
        else put(o,(char)*p);
    }
    put(o,'"');
}
static void dump(Output *o,const cJSON *v,int depth) {
    if(depth>12){o->failed=true;return;}
    if(!v||cJSON_IsNull(v))text(o,"null");
    else if(cJSON_IsTrue(v))text(o,"true");
    else if(cJSON_IsFalse(v))text(o,"false");
    else if(cJSON_IsString(v))quoted(o,v->valuestring);
    else if(cJSON_IsNumber(v)) {char b[64];if(!isfinite(v->valuedouble))text(o,"null");else{snprintf(b,sizeof(b),"%.17g",v->valuedouble);text(o,b);}}
    else if(cJSON_IsObject(v)||cJSON_IsArray(v)) {
        bool obj=cJSON_IsObject(v);put(o,obj?'{':'[');
        for(cJSON *c=v->child;c;c=c->next){if(c!=v->child)put(o,',');if(obj){quoted(o,c->string);put(o,':');}dump(o,c,depth+1);}
        put(o,obj?'}':']');
    } else o->failed=true;
}
char *pm_json_dump(const cJSON *v) {
    Output o={calloc(PM_COMMAND,1),0,false};if(!o.s)return NULL;
    dump(&o,v,0);if(o.failed){free(o.s);return NULL;}return o.s;
}
void pm_output_init(void){InitializeCriticalSection(&output_lock);}
void pm_emit(cJSON *o) {
    char *s=pm_json_dump(o);cJSON_Delete(o);
    if(s){EnterCriticalSection(&output_lock);fputs(s,stdout);fputc('\n',stdout);fflush(stdout);LeaveCriticalSection(&output_lock);free(s);}
}
void pm_reply(const cJSON *request,bool ok,const char *message,cJSON *result) {
    cJSON *o=cJSON_CreateObject();cJSON_AddNumberToObject(o,"v",1);cJSON_AddStringToObject(o,"id",pm_text(request,"id"));
    cJSON_AddBoolToObject(o,"ok",ok);cJSON_AddStringToObject(o,"message",message?message:"");
    if(result)cJSON_AddItemToObject(o,"result",result);
    pm_emit(o);
}
