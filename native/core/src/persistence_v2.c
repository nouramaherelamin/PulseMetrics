/* Single-writer SQLite implementation. All SQL formatting uses SQLite %Q quoting;
 * format strings are constants. A batch is never released on an error. */
#include "pm_db.h"
#include "pm_schema.h"
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static bool error(PmDb *d,const char *s) {snprintf(d->error,sizeof(d->error),"%s",s);return false;}
static bool execf(PmDb *d,const char *format,...) {
    va_list ap;va_start(ap,format);char *sql=sqlite3_vmprintf(format,ap);va_end(ap);
    if(!sql)return error(d,"out of memory");
    int rc=sqlite3_exec(d->sql,sql,NULL,NULL,NULL);sqlite3_free(sql);
    return rc==SQLITE_OK ? true : error(d,sqlite3_errmsg(d->sql));
}
static sqlite3_stmt *query(PmDb *d,const char *format,...) {
    va_list ap;va_start(ap,format);char *sql=sqlite3_vmprintf(format,ap);va_end(ap);
    sqlite3_stmt *s=NULL;
    if(!sql){error(d,"out of memory");return NULL;}
    if(sqlite3_prepare_v2(d->sql,sql,-1,&s,NULL)!=SQLITE_OK){error(d,sqlite3_errmsg(d->sql));s=NULL;}
    sqlite3_free(sql);return s;
}
static bool rollback(PmDb *d) {sqlite3_exec(d->sql,"ROLLBACK",NULL,NULL,NULL);return false;}
static bool commit(PmDb *d) {if(execf(d,"COMMIT"))return true;return rollback(d);}
static int64_t source_id(PmDb *d,const char *key) {
    sqlite3_stmt *s=query(d,"SELECT source_id FROM sources WHERE source_key=%Q",key);if(!s)return 0;
    int64_t id=sqlite3_step(s)==SQLITE_ROW?sqlite3_column_int64(s,0):0;sqlite3_finalize(s);return id;
}
static bool source(PmDb *d,const char *key,const char *kind,const char *label,int64_t pid,int64_t created,int64_t now,int64_t *id) {
    if(!pm_identifier(key,64)||!label||!strlen(label)||strlen(label)>1024)return error(d,"invalid source");
    bool process=!strcmp(kind,"process");
    sqlite3_stmt *s=query(d,"SELECT source_id,kind,pid,creation_filetime FROM sources WHERE source_key=%Q",key);
    if(!s)return false;
    int rc=sqlite3_step(s);
    if(rc==SQLITE_ROW) {
        *id=sqlite3_column_int64(s,0);
        bool same=!strcmp((const char*)sqlite3_column_text(s,1),kind);
        if(process)same=same && sqlite3_column_int64(s,2)==pid && sqlite3_column_int64(s,3)==created;
        sqlite3_finalize(s);if(!same)return error(d,"source identity conflict");
        return execf(d,"UPDATE sources SET display_name=%Q,last_seen_utc_us=%lld WHERE source_id=%lld",label,now,*id);
    }
    sqlite3_finalize(s);if(rc!=SQLITE_DONE)return error(d,sqlite3_errmsg(d->sql));
    if(process) {
        if(!execf(d,"INSERT INTO sources(source_key,kind,display_name,pid,creation_filetime,first_seen_utc_us,last_seen_utc_us) VALUES(%Q,%Q,%Q,%lld,%lld,%lld,%lld)",key,kind,label,pid,created,now,now))return false;
    } else if(!execf(d,"INSERT INTO sources(source_key,kind,display_name,first_seen_utc_us,last_seen_utc_us) VALUES(%Q,%Q,%Q,%lld,%lld)",key,kind,label,now,now))return false;
    *id=sqlite3_last_insert_rowid(d->sql);return true;
}
static bool metric(PmDb *d,PmStore *store,int64_t sid,const char *key,const char *name,PmKind kind,PmUnit unit) {
    if(!pm_identifier(name,128))return error(d,"invalid metric name");
    if(!execf(d,"INSERT INTO metrics(source_id,name,kind,unit) VALUES(%lld,%Q,%Q,%Q) ON CONFLICT(source_id,name) DO NOTHING",sid,name,pm_kind_name(kind),pm_unit_name(unit)))return false;
    sqlite3_stmt *s=query(d,"SELECT metric_id,kind,unit FROM metrics WHERE source_id=%lld AND name=%Q",sid,name);if(!s)return false;
    bool ok=false;
    if(sqlite3_step(s)==SQLITE_ROW && !strcmp((const char*)sqlite3_column_text(s,1),pm_kind_name(kind)) && !strcmp((const char*)sqlite3_column_text(s,2),pm_unit_name(unit)))
        ok=pm_register(store,sqlite3_column_int64(s,0),key,name,kind,unit);
    sqlite3_finalize(s);return ok?true:error(d,"metric contract conflict or active series capacity reached");
}
bool pm_db_open(PmDb *d,const char *path,const char *session,int64_t now,int sample,int window,int retention) {
    memset(d,0,sizeof(*d));d->retention_days=retention;
    if(!path||!session||strlen(session)>=sizeof(d->session)||sample<1||window<sample||window>60||retention<1||retention>30)return error(d,"invalid startup configuration");
    strcpy(d->session,session);
    if(sqlite3_open_v2(path,&d->sql,SQLITE_OPEN_READWRITE|SQLITE_OPEN_CREATE,NULL)!=SQLITE_OK)return error(d,"cannot open database");
    sqlite3_busy_timeout(d->sql,500);
    if(!execf(d,"PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL"))return false;
    sqlite3_stmt *s=query(d,"PRAGMA user_version");if(!s)return false;
    int version=sqlite3_step(s)==SQLITE_ROW?sqlite3_column_int(s,0):-1;sqlite3_finalize(s);
    if(version==0) {
        s=query(d,"SELECT count(*) FROM sqlite_master WHERE type='table'");if(!s)return false;
        int tables=sqlite3_step(s)==SQLITE_ROW?sqlite3_column_int(s,0):1;sqlite3_finalize(s);
        if(tables)return error(d,"unrecognized existing database; V1 import is not supported");
        if(sqlite3_exec(d->sql,pm_schema_sql,NULL,NULL,NULL)!=SQLITE_OK)return error(d,sqlite3_errmsg(d->sql));
    } else if(version!=1)return error(d,"unsupported schema version");
    s=query(d,"SELECT s.session_order,t.state,m.unit,w.elapsed_us,a.last_received_utc_us,r.enabled,e.closed_session_order,h.pending_batches FROM sessions s,tracking_intervals t,metrics m,windows w,aggregates a,alert_rules r,alert_events e,health_samples h LIMIT 0");
    if(!s)return error(d,"database schema objects are missing or incompatible");
    sqlite3_finalize(s);
    s=query(d,"PRAGMA journal_mode=WAL");if(!s)return false;
    bool wal=sqlite3_step(s)==SQLITE_ROW&&!strcmp((const char*)sqlite3_column_text(s,0),"wal");sqlite3_finalize(s);
    if(!wal)return error(d,"database requires WAL mode");
    s=query(d,"PRAGMA quick_check");if(!s)return false;
    bool healthy=sqlite3_step(s)==SQLITE_ROW&&!strcmp((const char*)sqlite3_column_text(s,0),"ok");sqlite3_finalize(s);
    if(!healthy)return error(d,"database integrity check failed");
    s=query(d,"SELECT max(t) FROM (SELECT max(started_utc_us) t FROM sessions UNION ALL SELECT max(end_utc_us) FROM windows)");if(!s)return false;
    if(sqlite3_step(s)==SQLITE_ROW)d->clock_warning=sqlite3_column_int64(s,0)>now;
    sqlite3_finalize(s);
    if(!execf(d,"BEGIN IMMEDIATE"))return false;
    if(!execf(d,"UPDATE sessions SET state='interrupted' WHERE state='running'; UPDATE tracking_intervals SET state='interrupted',end_reason='interrupted' WHERE state='active'"))return rollback(d);
    if(!execf(d,"INSERT INTO sessions(session_id,clock_warning,started_utc_us,state,window_seconds,sample_seconds,config_revision) VALUES(%Q,%d,%lld,'running',%d,%d,1)",session,d->clock_warning,now,window,sample))return rollback(d);
    d->session_order=sqlite3_last_insert_rowid(d->sql);return commit(d);
}
bool pm_db_seed(PmDb *d,PmStore *store,const cJSON *config,int64_t now) {
    if(!execf(d,"BEGIN IMMEDIATE"))return false;
    int64_t sid;
    if(!source(d,"system","system","This computer",0,0,now,&sid))return rollback(d);
    const char *names[]={"cpu.percent","memory.used","memory.total","memory.available","memory.percent"};
    for(int i=0;i<5;i++)if(!metric(d,store,sid,"system",names[i],PM_GAUGE,(i==0||i==4)?PM_PERCENT:PM_BYTES))return rollback(d);
    cJSON *sources=cJSON_GetObjectItemCaseSensitive(config,"sources");
    if(!cJSON_IsArray(sources)||cJSON_GetArraySize(sources)>32)return rollback(d);
    for(cJSON *a=sources->child;a;a=a->next) {
        const char *key=pm_text(a,"key");if(strncmp(key,"app.",4)||!source(d,key,"application",pm_text(a,"label"),0,0,now,&sid))return rollback(d);
        cJSON *metrics=cJSON_GetObjectItemCaseSensitive(a,"metrics");
        if(!cJSON_IsArray(metrics)||cJSON_GetArraySize(metrics)>32)return rollback(d);
        for(cJSON *m=metrics->child;m;m=m->next){PmKind kind;PmUnit unit;
            if(!pm_kind_parse(pm_text(m,"type"),&kind)||!pm_unit_parse(pm_text(m,"unit"),&unit)||!metric(d,store,sid,key,pm_text(m,"name"),kind,unit))return rollback(d);
        }
    }
    return commit(d);
}
static bool event_update(PmDb *d,const PmBatch *b,int64_t wid,const PmRow *row) {
    sqlite3_stmt *s=query(d,"SELECT r.rule_id,r.field,r.operator,r.threshold FROM alert_rules r JOIN metrics m USING(metric_id) JOIN sources s USING(source_id) WHERE r.metric_id=%lld AND r.enabled=1 AND (s.kind<>'process' OR s.selected=1)",row->metric_id);if(!s)return false;
    int rc;bool ok=true;
    while((rc=sqlite3_step(s))==SQLITE_ROW) {
        const char *id=(const char*)sqlite3_column_text(s,0),*field=(const char*)sqlite3_column_text(s,1),*op=(const char*)sqlite3_column_text(s,2);
        const PmStats *a=&row->stats;double v=a->last,limit=sqlite3_column_double(s,3);
        if(!strcmp(field,"sum"))v=a->sum;else if(!strcmp(field,"mean"))v=a->sum/a->count;
        else if(!strcmp(field,"min"))v=a->min;else if(!strcmp(field,"max"))v=a->max;
        else if(!strcmp(field,"rate"))v=pm_rate(row->kind,a,b->end_us-b->start_us);
        bool breach=!strcmp(op,"gt")?v>limit:!strcmp(op,"ge")?v>=limit:!strcmp(op,"lt")?v<limit:v<=limit;
        if(breach) {
            ok=execf(d,"INSERT INTO alert_events(rule_id,opened_session_order,last_session_order,opened_utc_us,last_evaluated_utc_us,first_window_id,last_window_id,opening_value,last_value) SELECT %Q,%lld,%lld,%lld,%lld,%lld,%lld,%!.17g,%!.17g WHERE NOT EXISTS(SELECT 1 FROM alert_events WHERE rule_id=%Q AND closed_utc_us IS NULL)",id,d->session_order,d->session_order,b->end_us,b->end_us,wid,wid,v,v,id);
            if(ok)ok=execf(d,"UPDATE alert_events SET last_session_order=%lld,last_evaluated_utc_us=%lld,last_window_id=%lld,last_value=%!.17g WHERE rule_id=%Q AND closed_utc_us IS NULL",d->session_order,b->end_us,wid,v,id);
        } else ok=execf(d,"UPDATE alert_events SET last_session_order=%lld,closed_session_order=%lld,last_evaluated_utc_us=%lld,closed_utc_us=%lld,close_reason='recovered',last_window_id=%lld,last_value=%!.17g WHERE rule_id=%Q AND closed_utc_us IS NULL",d->session_order,d->session_order,b->end_us,b->end_us,wid,v,id);
        if(!ok)break;
    }
    if(rc!=SQLITE_DONE&&ok)ok=error(d,sqlite3_errmsg(d->sql));
    sqlite3_finalize(s);return ok;
}
bool pm_db_batch(PmDb *d,const PmBatch *b,const PmHealth *h) {
    if(b->end_us<=b->start_us)return error(d,"invalid batch interval");
    if(!execf(d,"BEGIN IMMEDIATE"))return false;
    sqlite3_stmt *s=query(d,"SELECT start_utc_us,end_utc_us FROM windows WHERE session_id=%Q AND sequence=%lld",d->session,b->sequence);
    if(!s)return rollback(d);
    int rc=sqlite3_step(s);
    if(rc==SQLITE_ROW){bool same=sqlite3_column_int64(s,0)==b->start_us&&sqlite3_column_int64(s,1)==b->end_us;sqlite3_finalize(s);if(!same){error(d,"batch identity conflict");return rollback(d);}return commit(d);}
    sqlite3_finalize(s);if(rc!=SQLITE_DONE)return rollback(d);
    if(!execf(d,"INSERT INTO windows(session_id,sequence,start_utc_us,end_utc_us,elapsed_us,partial,committed_utc_us) VALUES(%Q,%lld,%lld,%lld,%lld,%d,%lld)",d->session,b->sequence,b->start_us,b->end_us,b->end_us-b->start_us,b->partial,pm_wall_us()))return rollback(d);
    int64_t wid=sqlite3_last_insert_rowid(d->sql);
    s=query(d,"INSERT INTO aggregates VALUES(?,?,?,?,?,?,?,?,?,?)");if(!s)return rollback(d);
    for(size_t i=0;i<b->count;i++) {
        const PmRow *r=&b->rows[i];const PmStats *a=&r->stats;
        sqlite3_bind_int64(s,1,wid);sqlite3_bind_int64(s,2,r->metric_id);sqlite3_bind_text(s,3,pm_kind_name(r->kind),-1,SQLITE_STATIC);
        sqlite3_bind_int64(s,4,(sqlite3_int64)a->count);sqlite3_bind_double(s,5,a->sum);sqlite3_bind_double(s,6,a->min);
        sqlite3_bind_double(s,7,a->max);sqlite3_bind_double(s,8,a->last);sqlite3_bind_int64(s,9,a->first_us);sqlite3_bind_int64(s,10,a->last_us);
        rc=sqlite3_step(s);sqlite3_reset(s);sqlite3_clear_bindings(s);
        if(rc!=SQLITE_DONE){error(d,sqlite3_errmsg(d->sql));sqlite3_finalize(s);return rollback(d);}
        if(!event_update(d,b,wid,r)){sqlite3_finalize(s);return rollback(d);}
    }
    sqlite3_finalize(s);
    if(!execf(d,"INSERT INTO health_samples VALUES(%lld,%lld,%lld,%lld,%lld,%lld,%lld,%lld,%d,%lld,%lld,%d)",wid,(int64_t)h->datagrams,(int64_t)h->bad_datagrams,(int64_t)h->lines,(int64_t)h->accepted,(int64_t)h->rejected,(int64_t)h->dropped,(int64_t)h->write_failures,h->pending,h->last_received,h->last_commit,h->clock_warning))return rollback(d);
    if(h->clock_warning&&!execf(d,"UPDATE sessions SET clock_warning=1 WHERE session_order=%lld",d->session_order))return rollback(d);
    if(!execf(d,"UPDATE sources SET last_seen_utc_us=(SELECT max(a.last_received_utc_us) FROM aggregates a JOIN metrics m ON m.metric_id=a.metric_id WHERE a.window_id=%lld AND m.source_id=sources.source_id) WHERE source_id IN(SELECT m.source_id FROM aggregates a JOIN metrics m ON m.metric_id=a.metric_id WHERE a.window_id=%lld)",wid,wid))return rollback(d);
    return commit(d);
}
static bool close_events(PmDb *d,int64_t sid,const char *rule,const char *reason,int64_t now) {
    return execf(d,"UPDATE alert_events SET closed_session_order=%lld,closed_utc_us=%lld,close_reason=%Q WHERE closed_utc_us IS NULL AND rule_id IN (SELECT rule_id FROM alert_rules WHERE (%lld=0 OR metric_id IN(SELECT metric_id FROM metrics WHERE source_id=%lld)) AND (%Q='' OR rule_id=%Q))",d->session_order,now,reason,sid,sid,rule,rule);
}
bool pm_db_command(PmDb *d,PmStore *store,const cJSON *req,int64_t now) {
    const char *op=pm_text(req,"op");cJSON *args=cJSON_GetObjectItemCaseSensitive(req,"args");
    if(!cJSON_IsObject(args))return error(d,"args must be an object");
    PmStore *candidate=malloc(sizeof(*candidate));if(!candidate)return error(d,"out of memory");
    memcpy(candidate,store,sizeof(*candidate));
    bool ok=execf(d,"BEGIN IMMEDIATE");if(!ok){free(candidate);return false;}
    if(!strcmp(op,"track")) {
        int64_t pid=0;char *end=NULL;const char *created_text=pm_text(args,"created");
        int64_t created=strtoll(created_text,&end,10);char key[65];
        ok=pm_integer(args,"pid",1,UINT32_MAX,&pid)&&created>0&&end&&!*end;
        snprintf(key,sizeof(key),"p.%lld.%lld",pid,created);
        sqlite3_stmt *s=query(d,"SELECT count(*) FROM sources WHERE selected=1 AND source_key<>%Q",key);
        if(!s)ok=false;else{if(sqlite3_step(s)!=SQLITE_ROW||sqlite3_column_int(s,0)>=100)ok=false;sqlite3_finalize(s);}
        int64_t sid=0;
        if(ok)ok=source(d,key,"process",pm_text(args,"label"),pid,created,now,&sid);
        if(ok)ok=metric(d,candidate,sid,key,"cpu.percent",PM_GAUGE,PM_PERCENT)&&metric(d,candidate,sid,key,"memory.working_set",PM_GAUGE,PM_BYTES);
        if(ok)ok=execf(d,"UPDATE sources SET selected=1,ended_utc_us=NULL WHERE source_id=%lld; INSERT INTO tracking_intervals(source_id,session_id,start_utc_us) SELECT %lld,%Q,%lld WHERE NOT EXISTS(SELECT 1 FROM tracking_intervals WHERE source_id=%lld AND state='active')",sid,sid,d->session,now,sid);
    } else if(!strcmp(op,"untrack")||!strcmp(op,"ended")) {
        const char *key=pm_text(args,"source");int64_t sid=source_id(d,key);ok=sid>0&&!strncmp(key,"p.",2);
        bool ended=!strcmp(op,"ended");
        if(ok)ok=execf(d,"UPDATE sources SET selected=0 WHERE source_id=%lld; UPDATE tracking_intervals SET state='closed',end_utc_us=%lld,end_reason=%Q WHERE source_id=%lld AND state='active'",sid,now,ended?"ended":"untracked",sid);
        if(ok&&ended)ok=execf(d,"UPDATE sources SET ended_utc_us=coalesce(ended_utc_us,%lld) WHERE source_id=%lld",now,sid)&&close_events(d,sid,"","source_ended",now);
        if(ok)for(size_t i=0;i<PM_SERIES;i++)if(!strcmp(candidate->series[i].source,key))candidate->series[i].enabled=false;
    } else if(!strcmp(op,"add_rule")) {
        const char *id=pm_text(req,"id"),*field=pm_text(args,"field"),*cmp=pm_text(args,"operator"),*label=pm_text(args,"label"),*severity=pm_text(args,"severity");
        int64_t mid=0;double limit=pm_number(args,"threshold",NAN);
        ok=strlen(id)==36&&pm_integer(args,"metric_id",1,INT64_MAX/2,&mid)&&isfinite(limit)&&fabs(limit)<=1e15&&strlen(label)>0&&strlen(label)<=120;
        if(ok) {
            sqlite3_stmt *s=query(d,"SELECT metric_id,field,operator,threshold,label,severity FROM alert_rules WHERE rule_id=%Q",id);
            if(!s)ok=false;else {
                int rc=sqlite3_step(s);
                if(rc==SQLITE_ROW)ok=sqlite3_column_int64(s,0)==mid&&!strcmp((const char*)sqlite3_column_text(s,1),field)&&!strcmp((const char*)sqlite3_column_text(s,2),cmp)&&sqlite3_column_double(s,3)==limit&&!strcmp((const char*)sqlite3_column_text(s,4),label)&&!strcmp((const char*)sqlite3_column_text(s,5),severity);
                else if(rc==SQLITE_DONE) {
                    sqlite3_stmt *capacity=query(d,"SELECT count(*) FROM alert_rules WHERE enabled=1");
                    ok=capacity&&sqlite3_step(capacity)==SQLITE_ROW&&sqlite3_column_int(capacity,0)<256;
                    sqlite3_finalize(capacity);
                    if(ok)ok=execf(d,"INSERT INTO alert_rules VALUES(%Q,%lld,%Q,%Q,%Q,%!.17g,%Q,1,%lld)",id,mid,label,field,cmp,limit,severity,now);
                    else error(d,"active alert rule limit (256) reached");
                }
                else ok=false;
                sqlite3_finalize(s);
            }
        }
    } else if(!strcmp(op,"disable_rule")) {
        const char *id=pm_text(args,"rule_id");
        ok=strlen(id)==36&&execf(d,"UPDATE alert_rules SET enabled=0 WHERE rule_id=%Q",id)&&close_events(d,0,id,"rule_disabled",now);
    } else ok=error(d,"unsupported command");
    if(ok)ok=commit(d);else {if(!d->error[0])error(d,"invalid command or resource limit");rollback(d);}
    if(ok)memcpy(store,candidate,sizeof(*store));
    free(candidate);return ok;
}
bool pm_db_finish(PmDb *d,int64_t now,bool clean) {
    if(!execf(d,"BEGIN IMMEDIATE"))return false;
    bool ok=execf(d,"UPDATE sessions SET state=%Q,ended_utc_us=%lld WHERE session_order=%lld",clean?"clean":"failed",now,d->session_order);
    if(ok)ok=execf(d,"UPDATE tracking_intervals SET state='closed',end_utc_us=%lld,end_reason='shutdown' WHERE session_id=%Q AND state='active'",now,d->session);
    return ok?commit(d):rollback(d);
}
void pm_db_retention(PmDb *d,int64_t now) {
    if(d->clock_warning)return; /* avoid expiring history against a discontinuous clock */
    int64_t cutoff=now-(int64_t)d->retention_days*86400000000LL;
    if(!execf(d,"BEGIN IMMEDIATE"))return;
    bool ok=execf(d,"DELETE FROM windows WHERE window_id IN(SELECT window_id FROM windows WHERE end_utc_us<%lld ORDER BY end_utc_us LIMIT 500)",cutoff);
    if(ok)ok=execf(d,"DELETE FROM alert_events WHERE event_id IN(SELECT event_id FROM alert_events WHERE closed_utc_us<%lld LIMIT 500)",cutoff);
    if(ok)ok=execf(d,"DELETE FROM tracking_intervals WHERE tracking_id IN(SELECT tracking_id FROM tracking_intervals WHERE state<>'active' AND coalesce(end_utc_us,start_utc_us)<%lld LIMIT 500)",cutoff);
    if(ok)ok=execf(d,"DELETE FROM alert_rules WHERE enabled=0 AND NOT EXISTS(SELECT 1 FROM alert_events e WHERE e.rule_id=alert_rules.rule_id)");
    if(ok)ok=execf(d,"DELETE FROM metrics WHERE source_id IN(SELECT source_id FROM sources WHERE kind='process' AND selected=0 AND last_seen_utc_us<%lld) AND NOT EXISTS(SELECT 1 FROM aggregates a WHERE a.metric_id=metrics.metric_id) AND NOT EXISTS(SELECT 1 FROM alert_rules r WHERE r.metric_id=metrics.metric_id)",cutoff);
    if(ok)ok=execf(d,"DELETE FROM sources WHERE kind='process' AND selected=0 AND last_seen_utc_us<%lld AND NOT EXISTS(SELECT 1 FROM metrics m WHERE m.source_id=sources.source_id) AND NOT EXISTS(SELECT 1 FROM tracking_intervals t WHERE t.source_id=sources.source_id)",cutoff);
    if(ok)ok=execf(d,"DELETE FROM sessions WHERE session_order<>%lld AND started_utc_us<%lld AND NOT EXISTS(SELECT 1 FROM windows w WHERE w.session_id=sessions.session_id) AND NOT EXISTS(SELECT 1 FROM tracking_intervals t WHERE t.session_id=sessions.session_id) AND NOT EXISTS(SELECT 1 FROM alert_events e WHERE e.opened_session_order=sessions.session_order OR e.last_session_order=sessions.session_order OR e.closed_session_order=sessions.session_order)",d->session_order,cutoff);
    if(ok)commit(d);else rollback(d);
    sqlite3_wal_checkpoint_v2(d->sql,NULL,SQLITE_CHECKPOINT_PASSIVE,NULL,NULL);
}
void pm_db_close(PmDb *d){if(d->sql){sqlite3_close(d->sql);d->sql=NULL;}}
