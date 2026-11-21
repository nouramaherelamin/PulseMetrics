#ifndef PM_JSON_H
#define PM_JSON_H
#include "cJSON.h"
#include <stdbool.h>
#include <stdint.h>
const char *pm_text(const cJSON *o, const char *key);
double pm_number(const cJSON *o, const char *key, double fallback);
bool pm_integer(const cJSON *o,const char *key,int64_t minimum,int64_t maximum,int64_t *out);
cJSON *pm_json_parse(const char *text);
char *pm_json_dump(const cJSON *value);
void pm_output_init(void);
void pm_emit(cJSON *object); /* takes ownership */
void pm_reply(const cJSON *request, bool ok, const char *message, cJSON *result);
#endif
