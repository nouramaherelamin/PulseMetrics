/* Standalone instrumentation example. Measures actual checksum work with QPC. */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <windows.h>
#include "pm.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <locale.h>

int main(int argc,char **argv) {
    if(argc!=3||strcmp(argv[1],"--port")){fprintf(stderr,"usage: pulse_sender --port PORT\n");return 2;}
    char *end=NULL;long port=strtol(argv[2],&end,10);if(*end||port<1024||port>65535)return 2;
    setlocale(LC_NUMERIC,"C");WSADATA ws;if(WSAStartup(MAKEWORD(2,2),&ws))return 2;
    SOCKET socket_fd=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);if(socket_fd==INVALID_SOCKET){WSACleanup();return 2;}
    struct sockaddr_in address={0};address.sin_family=AF_INET;address.sin_port=htons((u_short)port);address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    unsigned char buffer[65536];for(size_t i=0;i<sizeof(buffer);i++)buffer[i]=(unsigned char)i;
    unsigned attempts=0,failures=0;volatile uint64_t checksum=0;
    for(int operation=0;operation<5;operation++) {
        const char *busy="app.sender/in_flight:1|g";attempts++;
        if(sendto(socket_fd,busy,(int)strlen(busy),0,(struct sockaddr*)&address,sizeof(address))==SOCKET_ERROR)failures++;
        int64_t start=pm_mono_us();
        for(int pass=0;pass<4;pass++)for(size_t i=0;i<sizeof(buffer);i++)checksum=(checksum*33)^buffer[i];
        double elapsed_ms=(double)(pm_mono_us()-start)/1000.0;
        char packet[256];int n=snprintf(packet,sizeof(packet),"app.sender/operations:1|c\napp.sender/in_flight:0|g\napp.sender/operation_duration:%.6f|ms",elapsed_ms);attempts++;
        if(sendto(socket_fd,packet,n,0,(struct sockaddr*)&address,sizeof(address))!=n)failures++;
        printf("Operation %d: measured %.6f ms\n",operation+1,elapsed_ms);
    }
    printf("Completed 5 checksum operations; checksum=%llu; UDP attempts=%u failures=%u. Confirm receipt in collector history.\n",(unsigned long long)checksum,attempts,failures);
    closesocket(socket_fd);WSACleanup();return failures?1:0;
}
