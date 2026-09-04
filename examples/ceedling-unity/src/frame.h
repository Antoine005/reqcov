#ifndef FRAME_H
#define FRAME_H
#include <stdint.h>
#include <stddef.h>
typedef enum { FRAME_OK = 0, FRAME_ERR_LEN = 1, FRAME_ERR_CRC = 2 } frame_status_t;
frame_status_t frame_validate(const uint8_t *frame, size_t len);
#endif
