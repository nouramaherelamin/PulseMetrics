/* Counter/gauge/timer accumulation derived from received metrics.c.
 * A bounded array deliberately replaces unbounded allocation and partial hash snapshots. */
#include "pm.h"
#include <math.h>
#include <string.h>
bool pm_register(PmStore *s, int64_t id, const char *source, const char *name, PmKind kind, PmUnit unit) {
    if (!s || id <= 0 || !pm_identifier(source,64) || !pm_identifier(name,128)) return false;
    if (!((kind == PM_COUNTER && unit == PM_COUNT) || (kind == PM_TIMER && unit == PM_MS) ||
          (kind == PM_GAUGE && unit >= PM_COUNT && unit <= PM_UNIT && unit != PM_MS))) return false;
    PmSeries *slot = NULL;
    for (size_t i=0;i<PM_SERIES;i++) {
        PmSeries *e=&s->series[i];
        if (e->occupied && !strcmp(e->source,source) && !strcmp(e->name,name)) {
            if (e->id != id || e->kind != kind || e->unit != unit) return false;
            e->enabled=true; return true;
        }
        if (!slot && (!e->occupied || (!e->enabled && e->stats.count==0))) slot=e;
    }
    if (!slot) return false;
    memset(slot,0,sizeof(*slot)); slot->occupied=slot->enabled=true;
    slot->id=id; slot->kind=kind; slot->unit=unit;
    strcpy(slot->source,source); strcpy(slot->name,name); return true;
}
bool pm_update(PmStore *s, const PmInput *in, int64_t received) {
    if (!s || !in || !isfinite(in->value) || fabs(in->value)>1e12 || received<=0) return false;
    for (size_t i=0;i<PM_SERIES;i++) {
        PmSeries *e=&s->series[i];
        if (!e->occupied || strcmp(e->source,in->source) || strcmp(e->name,in->name)) continue;
        if (!e->enabled || e->kind!=in->kind) return false;
        double v=in->value;
        if ((e->unit!=PM_UNIT && v<0) || (e->unit==PM_PERCENT && v>100)) return false;
        PmStats *a=&e->stats;
        double sum=a->sum+v;
        if (a->count>=1000000 || !isfinite(sum) || fabs(sum)>1e15 || (a->count && received<a->last_us)) return false;
        if (!a->count) { a->min=a->max=v; a->first_us=received; }
        if (v<a->min) a->min=v;
        if (v>a->max) a->max=v;
        a->last=v; a->last_us=received; a->sum=sum; a->count++; return true;
    }
    return false;
}
void pm_snapshot(PmStore *s, PmBatch *b) {
    b->count=0;
    for (size_t i=0;i<PM_SERIES;i++) {
        PmSeries *e=&s->series[i];
        if (!e->occupied || !e->stats.count) continue;
        PmRow *r=&b->rows[b->count++]; r->metric_id=e->id; r->kind=e->kind; r->stats=e->stats;
        memset(&e->stats,0,sizeof(e->stats));
    }
}
double pm_rate(PmKind k, const PmStats *s, int64_t elapsed) {
    if (elapsed<=0 || k==PM_GAUGE) return NAN;
    return (k==PM_COUNTER ? s->sum : (double)s->count)*1e6/(double)elapsed;
}
