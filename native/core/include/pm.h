#ifndef PM_H
#define PM_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define PM_SERIES 1024
#define PM_PENDING 6
#define PM_LINE 256
#define PM_PACKET 1200
#define PM_COMMAND 65536
typedef enum { PM_COUNTER, PM_GAUGE, PM_TIMER } PmKind;
typedef enum { PM_COUNT, PM_PERCENT, PM_BYTES, PM_MS, PM_UNIT } PmUnit;
typedef struct { char source[65], name[129]; PmKind kind; double value; } PmInput;
typedef struct {
    uint64_t count;
    double sum, min, max, last;
    int64_t first_us, last_us;
} PmStats;
typedef struct {
    bool occupied, enabled;
    int64_t id;
    char source[65], name[129];
    PmKind kind;
    PmUnit unit;
    PmStats stats;
} PmSeries;
typedef struct { PmSeries series[PM_SERIES]; } PmStore;
typedef struct { int64_t metric_id; PmKind kind; PmStats stats; } PmRow;
typedef struct {
    int64_t sequence, start_us, end_us;
    bool partial;
    size_t count;
    PmRow rows[PM_SERIES];
} PmBatch;
bool pm_identifier(const char *s, size_t maximum);
bool pm_parse(const char *data, size_t length, PmInput *out);
const char *pm_kind_name(PmKind kind);
const char *pm_unit_name(PmUnit unit);
bool pm_kind_parse(const char *s, PmKind *out);
bool pm_unit_parse(const char *s, PmUnit *out);
bool pm_register(PmStore *store, int64_t id, const char *source, const char *name, PmKind kind, PmUnit unit);
bool pm_update(PmStore *store, const PmInput *input, int64_t received_us);
void pm_snapshot(PmStore *store, PmBatch *batch);
double pm_rate(PmKind kind, const PmStats *stats, int64_t elapsed_us);
int64_t pm_wall_us(void);
int64_t pm_mono_us(void);
#endif
