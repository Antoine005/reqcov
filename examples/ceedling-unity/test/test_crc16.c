#include "unity.h"
#include "crc16.h"

void setUp(void) {}
void tearDown(void) {}

/* @req LLR-10, HLR-1 */
void test_crc16_known_vector(void)
{
    const uint8_t msg[] = "123456789";
    TEST_ASSERT_EQUAL_HEX16(0x29B1, crc16_ccitt(msg, 9));
}

/* @req LLR-10 */
void test_crc16_empty_buffer_is_seed(void)
{
    TEST_ASSERT_EQUAL_HEX16(0xFFFF, crc16_ccitt((const uint8_t *)"", 0));
}
