/*
  Copyright (c) 2009-2017 Dave Gamble and cJSON contributors
  cJSON - Lightweight JSON parser in ANSI C
*/

#include "cJSON.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>
#include <float.h>
#include <limits.h>

static void *(*cJSON_malloc)(size_t sz) = malloc;
static void (*cJSON_free)(void *ptr) = free;

void cJSON_InitHooks(cJSON_Hooks* hooks) {
    if (!hooks) {
        cJSON_malloc = malloc;
        cJSON_free = free;
        return;
    }
    cJSON_malloc = (hooks->malloc_fn) ? hooks->malloc_fn : malloc;
    cJSON_free   = (hooks->free_fn) ? hooks->free_fn : free;
}

static cJSON *cJSON_New_Item(void) {
    cJSON* node = (cJSON*)cJSON_malloc(sizeof(cJSON));
    if (node) memset(node, '\0', sizeof(cJSON));
    return node;
}

void cJSON_Delete(cJSON *c) {
    cJSON *next;
    while (c) {
        next = c->next;
        if (!(c->type & cJSON_IsReference) && c->child) cJSON_Delete(c->child);
        if (!(c->type & cJSON_IsReference) && c->valuestring) cJSON_free(c->valuestring);
        if (!(c->type & cJSON_StringIsConst) && c->string) cJSON_free(c->string);
        cJSON_free(c);
        c = next;
    }
}

static const char *skip(const char *in) {
    while (in && (*in==' ' || *in=='\t' || *in=='\r' || *in=='\n')) in++;
    return in;
}

static const char *parse_value(cJSON *item, const char *value);
static const char *parse_string(cJSON *item, const char *str);
static const char *parse_number(cJSON *item, const char *num);
static const char *parse_array(cJSON *item, const char *value);
static const char *parse_object(cJSON *item, const char *value);

static const char *parse_number(cJSON *item, const char *num) {
    const char *p=num;
    if(*p=='-')p++;
    if(*p=='0')p++;
    else {if(*p<'1'||*p>'9')return NULL;while(*p>='0'&&*p<='9')p++;}
    if(*p=='.'){p++;if(*p<'0'||*p>'9')return NULL;while(*p>='0'&&*p<='9')p++;}
    if(*p=='e'||*p=='E'){p++;if(*p=='+'||*p=='-')p++;if(*p<'0'||*p>'9')return NULL;while(*p>='0'&&*p<='9')p++;}
    double n = 0;
    char *endptr = NULL;
    n = strtod(num, &endptr);
    if (endptr == num || endptr != p || !isfinite(n)) return NULL;
    item->valuedouble = n;
    item->valueint = n >= INT_MAX ? INT_MAX : n <= INT_MIN ? INT_MIN : (int)n;
    item->type = cJSON_Number;
    return endptr;
}

/* V2 safety patch to the received compact cJSON adaptation: bounded escapes/UTF-8. */
static unsigned hex4(const char *s) {
    unsigned n=0;
    for(int i=0;i<4;i++) {
        unsigned char c=(unsigned char)s[i]; unsigned x;
        if(c>='0'&&c<='9')x=c-'0';else if(c>='a'&&c<='f')x=c-'a'+10;
        else if(c>='A'&&c<='F')x=c-'A'+10;else return 0xffffffffu;
        n=(n<<4)|x;
    }
    return n;
}
static const char *parse_string(cJSON *item, const char *str) {
    if(!str || *str!='"') return NULL;
    const char *end=str+1;
    while(*end && *end!='"') {
        if((unsigned char)*end<32)return NULL;
        if(*end=='\\') {end++;if(!*end)return NULL;}
        end++;
    }
    if(*end!='"')return NULL;
    char *out=cJSON_malloc((size_t)(end-str)+1);if(!out)return NULL;
    char *q=out;const char *p=str+1;
    while(p<end) {
        if(*p!='\\'){*q++=*p++;continue;}
        p++;char ch=*p++;
        if(ch=='"'||ch=='\\'||ch=='/')*q++=ch;
        else if(ch=='n')*q++='\n';else if(ch=='r')*q++='\r';else if(ch=='t')*q++='\t';
        else if(ch=='b')*q++='\b';else if(ch=='f')*q++='\f';
        else if(ch=='u') {
            if(end-p<4)goto bad;
            unsigned cp=hex4(p);p+=4;if(cp==0xffffffffu||cp==0)goto bad;
            if(cp>=0xd800&&cp<=0xdbff) {
                if(end-p<6||p[0]!='\\'||p[1]!='u')goto bad;
                unsigned low=hex4(p+2);p+=6;if(low<0xdc00||low>0xdfff)goto bad;
                cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);
            } else if(cp>=0xdc00&&cp<=0xdfff)goto bad;
            if(cp<128)*q++=(char)cp;
            else if(cp<2048){*q++=(char)(0xc0|(cp>>6));*q++=(char)(0x80|(cp&63));}
            else if(cp<65536){*q++=(char)(0xe0|(cp>>12));*q++=(char)(0x80|((cp>>6)&63));*q++=(char)(0x80|(cp&63));}
            else{*q++=(char)(0xf0|(cp>>18));*q++=(char)(0x80|((cp>>12)&63));*q++=(char)(0x80|((cp>>6)&63));*q++=(char)(0x80|(cp&63));}
        } else goto bad;
    }
    *q=0;item->valuestring=out;item->type=cJSON_String;return end+1;
bad:cJSON_free(out);return NULL;
}

static const char *parse_array(cJSON *item, const char *value) {
    cJSON *child;
    if (*value != '[') return NULL;

    item->type = cJSON_Array;
    value = skip(value + 1);
    if (*value == ']') return value + 1;

    item->child = child = cJSON_New_Item();
    if (!item->child) return NULL;
    value = skip(parse_value(child, skip(value)));
    if (!value) return NULL;

    while (*value == ',') {
        cJSON *new_item = cJSON_New_Item();
        if (!new_item) return NULL;
        child->next = new_item;
        new_item->prev = child;
        child = new_item;
        value = skip(parse_value(child, skip(value + 1)));
        if (!value) return NULL;
    }

    if (*value == ']') return value + 1;
    return NULL;
}

static const char *parse_object(cJSON *item, const char *value) {
    cJSON *child;
    if (*value != '{') return NULL;

    item->type = cJSON_Object;
    value = skip(value + 1);
    if (*value == '}') return value + 1;

    item->child = child = cJSON_New_Item();
    if (!item->child) return NULL;
    value = skip(parse_string(child, skip(value)));
    if (!value) return NULL;
    child->string = child->valuestring;
    child->valuestring = NULL;
    if (*value != ':') return NULL;
    value = skip(parse_value(child, skip(value + 1)));
    if (!value) return NULL;

    while (*value == ',') {
        cJSON *new_item = cJSON_New_Item();
        if (!new_item) return NULL;
        child->next = new_item;
        new_item->prev = child;
        child = new_item;
        value = skip(parse_string(child, skip(value + 1)));
        if (!value) return NULL;
        child->string = child->valuestring;
        child->valuestring = NULL;
        if (*value != ':') return NULL;
        value = skip(parse_value(child, skip(value + 1)));
        if (!value) return NULL;
    }

    if (*value == '}') return value + 1;
    return NULL;
}

static const char *parse_value(cJSON *item, const char *value) {
    if (!value) return NULL;
    if (!strncmp(value, "null", 4))  { item->type = cJSON_NULL; return value + 4; }
    if (!strncmp(value, "false", 5)) { item->type = cJSON_False; return value + 5; }
    if (!strncmp(value, "true", 4))  { item->type = cJSON_True; item->valueint = 1; return value + 4; }
    if (*value == '\"')              { return parse_string(item, value); }
    if (*value == '-' || (*value >= '0' && *value <= '9')) { return parse_number(item, value); }
    if (*value == '[')              { return parse_array(item, value); }
    if (*value == '{')              { return parse_object(item, value); }
    return NULL;
}

cJSON *cJSON_Parse(const char *value) {
    return cJSON_ParseWithLength(value, value ? strlen(value) : 0);
}

cJSON *cJSON_ParseWithLength(const char *value, size_t buffer_length) {
    if (!value || !buffer_length || strlen(value) != buffer_length) return NULL;
    int depth=0; int quoted=0; int escaped=0;
    for (size_t i=0;i<buffer_length;i++) {
        unsigned char ch=(unsigned char)value[i];
        if (quoted) {
            if (escaped) { escaped=0; continue; }
            if (ch=='\\') { escaped=1; continue; }
            if (ch=='"') quoted=0;
            else if (ch<32) return NULL;
        } else {
            if (ch=='"') quoted=1;
            if (ch=='{' || ch=='[') { if (++depth>8) return NULL; }
            if (ch=='}' || ch==']') { if (--depth<0) return NULL; }
        }
    }
    if (quoted || escaped || depth) return NULL;
    cJSON *c = cJSON_New_Item();
    if (!c) return NULL;
    const char *end = parse_value(c, skip(value));
    if (!end || *skip(end)) { cJSON_Delete(c); return NULL; }
    return c;
}

cJSON *cJSON_GetObjectItem(const cJSON * const object, const char * const string) {
    cJSON *c = object ? object->child : NULL;
    while (c && c->string && _stricmp(c->string, string)) c = c->next;
    return c;
}

cJSON *cJSON_GetObjectItemCaseSensitive(const cJSON * const object, const char * const string) {
    cJSON *c = object ? object->child : NULL;
    while (c && c->string && strcmp(c->string, string)) c = c->next;
    return c;
}

int cJSON_HasObjectItem(const cJSON *object, const char *string) {
    return cJSON_GetObjectItem(object, string) ? 1 : 0;
}

int cJSON_GetArraySize(const cJSON *array) {
    cJSON *c = array ? array->child : NULL;
    int i = 0;
    while (c) i++, c = c->next;
    return i;
}

cJSON *cJSON_GetArrayItem(const cJSON *array, int index) {
    cJSON *c = array ? array->child : NULL;
    while (c && index > 0) index--, c = c->next;
    return c;
}

cJSON *cJSON_CreateNull(void)   { cJSON *item = cJSON_New_Item(); if (item) item->type = cJSON_NULL; return item; }
cJSON *cJSON_CreateTrue(void)   { cJSON *item = cJSON_New_Item(); if (item) { item->type = cJSON_True; item->valueint = 1; } return item; }
cJSON *cJSON_CreateFalse(void)  { cJSON *item = cJSON_New_Item(); if (item) item->type = cJSON_False; return item; }
cJSON *cJSON_CreateBool(int b)  { return b ? cJSON_CreateTrue() : cJSON_CreateFalse(); }
cJSON *cJSON_CreateNumber(double num) {
    cJSON *item = cJSON_New_Item();
    if (item) { item->type = cJSON_Number; item->valuedouble = num; item->valueint = num >= INT_MAX ? INT_MAX : num <= INT_MIN ? INT_MIN : (int)num; }
    return item;
}
cJSON *cJSON_CreateString(const char *string) {
    cJSON *item = cJSON_New_Item();
    if (item) {
        item->type = cJSON_String;
        item->valuestring = _strdup(string);
    }
    return item;
}
cJSON *cJSON_CreateArray(void)  { cJSON *item = cJSON_New_Item(); if (item) item->type = cJSON_Array; return item; }
cJSON *cJSON_CreateObject(void) { cJSON *item = cJSON_New_Item(); if (item) item->type = cJSON_Object; return item; }

void cJSON_AddItemToArray(cJSON *array, cJSON *item) {
    if (!array || !item) return;
    if (!array->child) {
        array->child = item;
    } else {
        cJSON *c = array->child;
        while (c->next) c = c->next;
        c->next = item;
        item->prev = c;
    }
}

void cJSON_AddItemToObject(cJSON *object, const char *string, cJSON *item) {
    if (!object || !string || !item) return;
    if (item->string) cJSON_free(item->string);
    item->string = _strdup(string);
    cJSON_AddItemToArray(object, item);
}

