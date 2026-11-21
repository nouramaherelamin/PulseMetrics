#include "pm.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void parse(PmStore *s,const char *line,int64_t time) {
    PmInput in; assert(pm_parse(line,strlen(line),&in)); assert(pm_update(s,&in,time));
}
int main(void) {
    PmInput in;
    const char *bad[]={"","a/x:abc|g","a/x:nan|g","a/x:inf|g","a/x:1e999|g","a/x:2|c garbage","a/x:0x10|g","a/x:1 |g","a/x:-1|ms","a/x:+2|c","a/x:2.|g","a//x:2|g","a/x:1|g|x","x:1|c"};
    for(size_t i=0;i<sizeof(bad)/sizeof(*bad);i++) assert(!pm_parse(bad[i],strlen(bad[i]),&in));
    assert(!pm_parse("a/x:1|g\0tail",12,&in));
    assert(pm_parse("app.a/x:1.25e-2|g\r",strlen("app.a/x:1.25e-2|g\r"),&in));
    assert(fabs(in.value-0.0125)<1e-12);
    PmStore *s=calloc(1,sizeof(*s)); PmBatch *b=calloc(1,sizeof(*b)); assert(s&&b);
    assert(pm_register(s,1,"a","counter",PM_COUNTER,PM_COUNT));
    assert(pm_register(s,2,"a","gauge",PM_GAUGE,PM_UNIT));
    assert(pm_register(s,3,"a","timer",PM_TIMER,PM_MS));
    assert(pm_register(s,4,"b","counter",PM_COUNTER,PM_COUNT));
    parse(s,"a/counter:2|c",1);parse(s,"a/counter:3|c",2);parse(s,"b/counter:7|c",2);
    parse(s,"a/gauge:4|g",1);parse(s,"a/gauge:9|g",2);
    parse(s,"a/timer:10|ms",1);parse(s,"a/timer:30|ms",2);parse(s,"a/timer:50|ms",3);
    assert(pm_parse("a/counter:99|g",strlen("a/counter:99|g"),&in)); assert(!pm_update(s,&in,4));
    pm_snapshot(s,b);assert(b->count==4);
    assert(b->rows[0].stats.sum==5 && b->rows[0].stats.min==2 && b->rows[0].stats.max==3);
    assert(pm_rate(PM_COUNTER,&b->rows[0].stats,10000000)==0.5);
    assert(pm_rate(PM_COUNTER,&b->rows[0].stats,1000000)==5);
    assert(b->rows[1].stats.last==9 && b->rows[1].stats.sum/b->rows[1].stats.count==6.5);
    assert(b->rows[2].stats.sum==90 && b->rows[2].stats.count==3);
    assert(b->rows[2].stats.min==10 && b->rows[2].stats.max==50);
    assert(fabs(pm_rate(PM_TIMER,&b->rows[2].stats,10000000)-0.3)<1e-12);
    assert(b->rows[3].stats.sum==7);pm_snapshot(s,b);assert(b->count==0);
    parse(s,"a/gauge:50|g",5);pm_snapshot(s,b);
    assert(b->count==1 && b->rows[0].stats.count==1);
    assert(b->rows[0].stats.min==50 && b->rows[0].stats.max==50 && b->rows[0].stats.last==50);
    for(int i=4;i<PM_SERIES;i++) {char n[32];snprintf(n,sizeof(n),"metric%d",i);assert(pm_register(s,i+1,"a",n,PM_GAUGE,PM_UNIT));}
    assert(!pm_register(s,9000,"a","overflow",PM_GAUGE,PM_UNIT));
    for(int i=4;i<PM_SERIES;i++) {char line[64];snprintf(line,sizeof(line),"a/metric%d:1|g",i);parse(s,line,10);}
    pm_snapshot(s,b);assert(b->count==PM_SERIES-4); /* inactive entries do not starve any series */
    char longname[130];memset(longname,'x',128);longname[128]=0;assert(pm_identifier(longname,128));longname[128]='x';longname[129]=0;assert(!pm_identifier(longname,128));
    free(s);free(b);puts("strict protocol, independent arithmetic, sources and bounded complete snapshots passed");return 0;
}
