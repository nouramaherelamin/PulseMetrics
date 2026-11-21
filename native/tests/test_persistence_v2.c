#include "pm_db.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int64_t scalar(PmDb *d,const char *sql) {
    sqlite3_stmt *s=NULL;
    assert(sqlite3_prepare_v2(d->sql,sql,-1,&s,NULL)==SQLITE_OK);
    assert(sqlite3_step(s)==SQLITE_ROW);
    int64_t n=sqlite3_column_int64(s,0);
    sqlite3_finalize(s);
    return n;
}
static void command(PmDb *d,PmStore *store,const char *json,int64_t now) {
    cJSON *o=pm_json_parse(json);assert(o);
    if(!pm_db_command(d,store,o,now)){fprintf(stderr,"%s\n",d->error);abort();}
    cJSON_Delete(o);
}
int main(void) {
    const char *file="recovery.sqlite";
    remove(file);remove("recovery.sqlite-wal");remove("recovery.sqlite-shm");
    PmDb d;PmHealth h={0};
    PmStore *store=calloc(1,sizeof(*store));PmBatch *b=calloc(1,sizeof(*b));assert(store&&b);
    const int64_t later=2000000000000000LL,earlier=later-86400000000LL;
    assert(pm_db_open(&d,file,"first",later,1,1,7));
    cJSON *config=pm_json_parse("{\"sources\":[]}");assert(config);
    assert(pm_db_seed(&d,store,config,later));
    command(&d,store,"{\"id\":\"00000000-0000-0000-0000-000000000001\",\"op\":\"add_rule\",\"args\":{\"metric_id\":1,\"field\":\"last\",\"operator\":\"gt\",\"threshold\":50,\"label\":\"CPU threshold\",\"severity\":\"warning\"}}",later);
    PmInput in={"system","cpu.percent",PM_GAUGE,80};
    assert(pm_update(store,&in,later+500));
    b->start_us=later;b->end_us=later+1000000;pm_snapshot(store,b);
    /* A real SQLite refusal must not persist a partial batch. */
    assert(sqlite3_exec(d.sql,"PRAGMA query_only=ON",NULL,NULL,NULL)==SQLITE_OK);
    assert(!pm_db_batch(&d,b,&h));
    assert(scalar(&d,"SELECT count(*) FROM windows")==0);
    assert(sqlite3_exec(d.sql,"PRAGMA query_only=OFF",NULL,NULL,NULL)==SQLITE_OK);
    assert(pm_db_batch(&d,b,&h));assert(pm_db_batch(&d,b,&h));
    assert(scalar(&d,"SELECT count(*) FROM windows")==1);
    assert(scalar(&d,"SELECT count(*) FROM alert_events WHERE closed_utc_us IS NULL")==1);
    /* Tracking starts after the last committed boundary. No end can be inferred. */
    command(&d,store,"{\"op\":\"track\",\"args\":{\"pid\":123,\"created\":\"123456789012345678\",\"label\":\"fixture\"}}",later+2000000);
    pm_db_close(&d);
    memset(store,0,sizeof(*store));
    assert(pm_db_open(&d,file,"second",earlier,1,1,7));assert(d.clock_warning);
    assert(pm_db_seed(&d,store,config,earlier));
    assert(scalar(&d,"SELECT count(*) FROM tracking_intervals WHERE state='interrupted' AND end_utc_us IS NULL AND start_utc_us=2000000002000000")==1);
    assert(scalar(&d,"SELECT session_order FROM sessions WHERE session_id='second'")==2);
    in.value=20;assert(pm_update(store,&in,earlier+500));
    b->sequence=0;b->start_us=earlier;b->end_us=earlier+1000000;pm_snapshot(store,b);
    assert(pm_db_batch(&d,b,&h));
    assert(scalar(&d,"SELECT count(*) FROM alert_events WHERE closed_utc_us<opened_utc_us AND opened_session_order=1 AND closed_session_order=2 AND close_reason='recovered'")==1);
    assert(scalar(&d,"SELECT count(*) FROM pragma_foreign_key_check")==0);
    assert(pm_db_finish(&d,earlier+3000000,true));
    pm_db_retention(&d,later+20*86400000000LL);
    assert(scalar(&d,"SELECT count(*) FROM windows")==2); /* rollback warning pauses expiry */
    pm_db_close(&d);
    const int64_t newest=later+9*86400000000LL;
    memset(store,0,sizeof(*store));
    assert(pm_db_open(&d,file,"third",newest,1,1,7));assert(!d.clock_warning);
    assert(pm_db_seed(&d,store,config,newest));
    in.value=80;assert(pm_update(store,&in,newest+500));
    b->sequence=0;b->start_us=newest;b->end_us=newest+1000000;pm_snapshot(store,b);
    assert(pm_db_batch(&d,b,&h));
    pm_db_retention(&d,newest+8*86400000000LL);
    assert(scalar(&d,"SELECT count(*) FROM windows")==0);
    assert(scalar(&d,"SELECT count(*) FROM aggregates")==0);
    assert(scalar(&d,"SELECT count(*) FROM alert_events WHERE closed_utc_us IS NULL AND first_window_id IS NULL AND opening_value=80")==1);
    assert(scalar(&d,"SELECT count(*) FROM pragma_foreign_key_check")==0);
    const int64_t resumed=newest+8*86400000000LL;
    command(&d,store,"{\"op\":\"track\",\"args\":{\"pid\":123,\"created\":\"123456789012345678\",\"label\":\"fixture\"}}",resumed);
    command(&d,store,"{\"id\":\"00000000-0000-0000-0000-000000000002\",\"op\":\"add_rule\",\"args\":{\"metric_id\":6,\"field\":\"last\",\"operator\":\"gt\",\"threshold\":0,\"label\":\"Ended source\",\"severity\":\"warning\"}}",resumed);
    PmInput process={"p.123.123456789012345678","cpu.percent",PM_GAUGE,10};
    assert(pm_update(store,&process,resumed+10));
    command(&d,store,"{\"op\":\"ended\",\"args\":{\"source\":\"p.123.123456789012345678\"}}",resumed+20);
    command(&d,store,"{\"op\":\"ended\",\"args\":{\"source\":\"p.123.123456789012345678\"}}",resumed+30);
    assert(scalar(&d,"SELECT ended_utc_us FROM sources WHERE pid=123")==resumed+20);
    b->sequence=1;b->start_us=resumed;b->end_us=resumed+100;pm_snapshot(store,b);
    assert(pm_db_batch(&d,b,&h));
    assert(scalar(&d,"SELECT count(*) FROM alert_events WHERE rule_id='00000000-0000-0000-0000-000000000002'")==0);
    pm_db_close(&d);cJSON_Delete(config);free(store);free(b);
    /* Received compact JSON parser: strict controls, escapes, duplicate fields. */
    assert(!pm_json_parse("{\"a\":1,\"a\":2}"));
    assert(!pm_json_parse("{\"a\":NaN}"));
    assert(!pm_json_parse("{\"a\":01}"));
    assert(!pm_json_parse("{\"a\":0x12}"));
    assert(!pm_json_parse("{\"a\":1.}"));
    assert(!pm_json_parse("{\"a\":1} trailing"));
    assert(!pm_json_parse("\"\\u0000\""));
    cJSON *j=pm_json_parse("{\"label\":\"C:\\\\work \\u03bb \\ud83d\\ude80\"}");assert(j);
    char *text=pm_json_dump(j);assert(text);cJSON *round=pm_json_parse(text);assert(round);
    assert(!strcmp(pm_text(j,"label"),pm_text(round,"label")));
    free(text);cJSON_Delete(j);cJSON_Delete(round);
    puts("Persistence, interrupted tracking, clock rollback and JSON contracts passed");return 0;
}
