#include "unity.h"
#include "frame.h"
#include "crc16.h"

void setUp(void) {}
void tearDown(void) {}

/* @req LLR-11, HLR-3 */
void test_frame_too_short_is_rejected(void)
{
    const uint8_t f[2] = {0x00, 0x00};
    TEST_ASSERT_EQUAL(FRAME_ERR_LEN, frame_validate(f, 2));
}

/* @req LLR-12, HLR-2 */
void test_frame_bad_crc_is_rejected(void)
{
    const uint8_t f[5] = {1, 2, 3, 0xDE, 0xAD};
    TEST_ASSERT_EQUAL(FRAME_ERR_CRC, frame_validate(f, 5));
}

/* @req LLR-12 */
void test_frame_good_crc_is_accepted(void)
{
    uint8_t f[5] = {1, 2, 3, 0, 0};
    uint16_t c = crc16_ccitt(f, 3);
    f[3] = (uint8_t)(c >> 8); f[4] = (uint8_t)c;
    TEST_ASSERT_EQUAL(FRAME_OK, frame_validate(f, 5));
}
