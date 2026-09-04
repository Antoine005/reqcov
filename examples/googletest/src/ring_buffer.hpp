#pragma once
#include <array>
#include <cstddef>

// @implements SWR-1, SWR-2, SWR-3, SWR-4
template <typename T, std::size_t N>
class RingBuffer {
public:
    bool push(const T& v) {
        std::size_t next = (head_ + 1) % (N + 1);
        if (next == tail_) return false;
        buf_[head_] = v; head_ = next; return true;
    }
    bool pop(T& out) {
        if (tail_ == head_) return false;
        out = buf_[tail_]; tail_ = (tail_ + 1) % (N + 1); return true;
    }
    std::size_t capacity() const { return N; }
private:
    std::array<T, N + 1> buf_{};
    std::size_t head_ = 0, tail_ = 0;
};
