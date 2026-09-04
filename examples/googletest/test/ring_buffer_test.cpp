#include <gtest/gtest.h>
#include "ring_buffer.hpp"

// @verifies SWR-1
TEST(RingBuffer, StoresCapacityElements) {
    RingBuffer<int, 4> rb;
    for (int i = 0; i < 4; ++i) EXPECT_TRUE(rb.push(i));
}

// @verifies SWR-2
TEST(RingBuffer, PushOnFullFails) {
    RingBuffer<int, 2> rb;
    rb.push(1); rb.push(2);
    EXPECT_FALSE(rb.push(3));
    int v; rb.pop(v); EXPECT_EQ(v, 1);
}

// @verifies SWR-3
TEST(RingBuffer, PopOnEmptyFails) {
    RingBuffer<int, 2> rb;
    int v;
    EXPECT_FALSE(rb.pop(v));
}
