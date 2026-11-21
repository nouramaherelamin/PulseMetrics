#include "pm.h"
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
int64_t pm_wall_us(void) {
    FILETIME ft; ULARGE_INTEGER v;
    GetSystemTimePreciseAsFileTime(&ft); v.LowPart=ft.dwLowDateTime; v.HighPart=ft.dwHighDateTime;
    return (int64_t)(v.QuadPart/10)-11644473600000000LL;
}
int64_t pm_mono_us(void) {
    LARGE_INTEGER n,f; QueryPerformanceCounter(&n); QueryPerformanceFrequency(&f);
    return (n.QuadPart/f.QuadPart)*1000000 + (n.QuadPart%f.QuadPart)*1000000/f.QuadPart;
}
