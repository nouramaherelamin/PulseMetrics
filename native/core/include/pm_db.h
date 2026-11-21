#ifndef PM_DB_H
#define PM_DB_H
#include "pm.h"
#include "pm_json.h"
#include "sqlite3.h"
typedef struct {
    sqlite3 *sql;
    int64_t session_order;
    char session[80], error[256];
    int retention_days;
    bool clock_warning;
} PmDb;
typedef struct {
    uint64_t datagrams, bad_datagrams, lines, accepted, rejected, dropped, write_failures;
    int pending;
    int64_t last_received, last_commit;
    bool clock_warning;
} PmHealth;
bool pm_db_open(PmDb *db,const char *path,const char *session,int64_t now,int sample,int window,int retention);
bool pm_db_seed(PmDb *db,PmStore *store,const cJSON *config,int64_t now);
bool pm_db_batch(PmDb *db,const PmBatch *batch,const PmHealth *health);
bool pm_db_command(PmDb *db,PmStore *store,const cJSON *request,int64_t now);
bool pm_db_finish(PmDb *db,int64_t now,bool clean);
void pm_db_retention(PmDb *db,int64_t now);
void pm_db_close(PmDb *db);
#endif
