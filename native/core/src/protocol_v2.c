/* Adapted from the received delimiter parser; exact grammar replaces permissive strtod parsing. */
#include "pm.h"
#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
static bool digit(char c) { return c >= '0' && c <= '9'; }
static bool letter(char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); }
bool pm_identifier(const char *s, size_t maximum) {
    if (!s || !letter(*s)) return false;
    size_t n = 0;
    for (; s[n]; n++) {
        if (n >= maximum || !(letter(s[n]) || digit(s[n]) || s[n] == '.' || s[n] == '_' || s[n] == '-')) return false;
    }
    return n > 0;
}
const char *pm_kind_name(PmKind k) {
    static const char *names[] = {"counter", "gauge", "timer"};
    return k >= PM_COUNTER && k <= PM_TIMER ? names[k] : "invalid";
}
const char *pm_unit_name(PmUnit u) {
    static const char *names[] = {"count", "percent", "bytes", "ms", "unit"};
    return u >= PM_COUNT && u <= PM_UNIT ? names[u] : "invalid";
}
bool pm_kind_parse(const char *s, PmKind *out) {
    for (int k = 0; k < 3; k++) if (s && strcmp(s, pm_kind_name(k)) == 0) { *out = k; return true; }
    return false;
}
bool pm_unit_parse(const char *s, PmUnit *out) {
    for (int u = 0; u < 5; u++) if (s && strcmp(s, pm_unit_name(u)) == 0) { *out = u; return true; }
    return false;
}
bool pm_parse(const char *data, size_t length, PmInput *out) {
    if (!data || !out || length == 0 || length > PM_LINE || memchr(data, 0, length)) return false;
    if (data[length-1] == '\r') length--;
    char line[PM_LINE+1]; memcpy(line, data, length); line[length] = 0;
    char *slash = strchr(line, '/'), *colon = strchr(line, ':'), *pipe = strchr(line, '|');
    if (!slash || !colon || !pipe || slash >= colon || colon >= pipe) return false;
    *slash = 0; *colon = 0; *pipe = 0;
    if (!pm_identifier(line, 64) || !pm_identifier(slash+1, 128)) return false;
    const char *p = colon+1;
    if (*p == '-') p++;
    if (!digit(*p)) return false;
    while (digit(*p)) p++;
    if (*p == '.') { p++; if (!digit(*p)) return false; while (digit(*p)) p++; }
    if (*p == 'e' || *p == 'E') {
        p++; if (*p == '+' || *p == '-') p++;
        if (!digit(*p)) return false;
        while (digit(*p)) p++;
    }
    if (*p) return false;
    errno = 0; char *end = NULL;
    double v = strtod(colon+1, &end);
    if (errno == ERANGE || !end || *end || !isfinite(v) || fabs(v) > 1e12) return false;
    PmKind k;
    if (strcmp(pipe+1, "c") == 0) k = PM_COUNTER;
    else if (strcmp(pipe+1, "g") == 0) k = PM_GAUGE;
    else if (strcmp(pipe+1, "ms") == 0) k = PM_TIMER;
    else return false;
    if (k != PM_GAUGE && v < 0) return false;
    strcpy(out->source, line); strcpy(out->name, slash+1); out->kind = k; out->value = v;
    return true;
}
