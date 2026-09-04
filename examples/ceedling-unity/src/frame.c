#include "frame.h"
#include "crc16.h"

/* @implements LLR-11, LLR-12 */
frame_status_t frame_validate(const uint8_t *frame, size_t len)
{
    if (len < 3u) {
        return FRAME_ERR_LEN;
    }
    uint16_t expected = (uint16_t)(((uint16_t)frame[len - 2] << 8) | frame[len - 1]);
    uint16_t actual = crc16_ccitt(frame, len - 2);
    return (expected == actual) ? FRAME_OK : FRAME_ERR_CRC;
}
