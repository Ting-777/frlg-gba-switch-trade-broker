// SPDX-License-Identifier: GPL-3.0-or-later
#include "sha256.hpp"

#include <array>
#include <cstddef>

namespace tradebroker {
namespace {

constexpr std::array<uint32_t, 64> k{
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

constexpr uint32_t rotateRight(uint32_t value, unsigned bits) {
    return (value >> bits) | (value << (32 - bits));
}

void transform(std::array<uint32_t, 8>& state, const uint8_t* block) {
    std::array<uint32_t, 64> w{};
    for (size_t i = 0; i < 16; ++i) {
        const size_t j = i * 4;
        w[i] = (static_cast<uint32_t>(block[j]) << 24) |
               (static_cast<uint32_t>(block[j + 1]) << 16) |
               (static_cast<uint32_t>(block[j + 2]) << 8) |
               static_cast<uint32_t>(block[j + 3]);
    }
    for (size_t i = 16; i < w.size(); ++i) {
        const uint32_t s0 = rotateRight(w[i - 15], 7) ^ rotateRight(w[i - 15], 18) ^
                            (w[i - 15] >> 3);
        const uint32_t s1 = rotateRight(w[i - 2], 17) ^ rotateRight(w[i - 2], 19) ^
                            (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }

    auto [a, b, c, d, e, f, g, h] = state;
    for (size_t i = 0; i < w.size(); ++i) {
        const uint32_t sum1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
        const uint32_t choice = (e & f) ^ (~e & g);
        const uint32_t t1 = h + sum1 + choice + k[i] + w[i];
        const uint32_t sum0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
        const uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        const uint32_t t2 = sum0 + majority;
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = c;
        c = b;
        b = a;
        a = t1 + t2;
    }
    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}

} // namespace

std::array<uint8_t, 32> sha256(std::span<const uint8_t> bytes) {
    std::array<uint32_t, 8> state{
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    };
    size_t offset = 0;
    while (bytes.size() - offset >= 64) {
        transform(state, bytes.data() + offset);
        offset += 64;
    }

    std::array<uint8_t, 128> tail{};
    const size_t remaining = bytes.size() - offset;
    for (size_t i = 0; i < remaining; ++i) tail[i] = bytes[offset + i];
    tail[remaining] = 0x80;
    const size_t padded = remaining < 56 ? 64 : 128;
    const uint64_t bitLength = static_cast<uint64_t>(bytes.size()) * 8;
    for (size_t i = 0; i < 8; ++i) {
        tail[padded - 1 - i] = static_cast<uint8_t>(bitLength >> (i * 8));
    }
    transform(state, tail.data());
    if (padded == 128) transform(state, tail.data() + 64);

    std::array<uint8_t, 32> digest{};
    for (size_t i = 0; i < state.size(); ++i) {
        digest[i * 4] = static_cast<uint8_t>(state[i] >> 24);
        digest[i * 4 + 1] = static_cast<uint8_t>(state[i] >> 16);
        digest[i * 4 + 2] = static_cast<uint8_t>(state[i] >> 8);
        digest[i * 4 + 3] = static_cast<uint8_t>(state[i]);
    }
    return digest;
}

} // namespace tradebroker
