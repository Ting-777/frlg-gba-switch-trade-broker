// SPDX-License-Identifier: GPL-3.0-or-later
#include "../../gb-link/broker_protocol.hpp"
#include "../../gb-link/sha256.hpp"

#include <array>
#include <cstdio>
#include <string_view>
#include <vector>

using namespace tradebroker;

namespace {
int failures = 0;

#define CHECK(condition) do { \
    if (!(condition)) { \
        std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        ++failures; \
    } \
} while (0)

struct Seen {
    Message type;
    uint32_t sequence;
    bool replayed;
};

bool captureChunk(void* context, std::span<const uint8_t> chunk) {
    auto& bytes = *static_cast<std::vector<uint8_t>*>(context);
    bytes.insert(bytes.end(), chunk.begin(), chunk.end());
    return true;
}

void captureFrame(void* context, const ParsedFrame& frame) {
    static_cast<std::vector<Seen>*>(context)->push_back(
        Seen{frame.type, frame.sequence, frame.replayed});
}

void testSha256() {
    const auto empty = sha256({});
    constexpr std::array<uint8_t, 32> expectedEmpty{
        0xe3,0xb0,0xc4,0x42,0x98,0xfc,0x1c,0x14,0x9a,0xfb,0xf4,0xc8,0x99,0x6f,0xb9,0x24,
        0x27,0xae,0x41,0xe4,0x64,0x9b,0x93,0x4c,0xa4,0x95,0x99,0x1b,0x78,0x52,0xb8,0x55,
    };
    CHECK(empty == expectedEmpty);

    constexpr std::string_view abc = "abc";
    const auto digest = sha256(std::span(
        reinterpret_cast<const uint8_t*>(abc.data()), abc.size()));
    constexpr std::array<uint8_t, 32> expectedAbc{
        0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,
        0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad,
    };
    CHECK(digest == expectedAbc);
}

void testHandshakeAndReplay() {
    std::vector<Seen> seen;
    std::vector<uint8_t> ignored;
    Codec receiver(captureFrame, &seen, captureChunk, &ignored);

    std::vector<uint8_t> encoded;
    Codec sender(captureFrame, &seen, captureChunk, &encoded);
    constexpr std::array<uint8_t, 16> txid{
        1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,
    };
    sender.setTransaction(txid);
    CHECK(sender.send(Message::hello));
    receiver.feed(encoded);
    CHECK(seen.size() == 1);
    CHECK(seen[0].type == Message::hello);
    CHECK(seen[0].sequence == 1);
    CHECK(!seen[0].replayed);

    receiver.feed(encoded);
    CHECK(seen.size() == 2);
    CHECK(seen[1].replayed);

    encoded.clear();
    CHECK(sender.send(Message::getCapabilities));
    receiver.feed(std::span(encoded).first(11));
    CHECK(seen.size() == 2);
    receiver.feed(std::span(encoded).subspan(11));
    CHECK(seen.size() == 3);
    CHECK(seen[2].type == Message::getCapabilities);
    CHECK(!seen[2].replayed);
}
} // namespace

int main() {
    testSha256();
    testHandshakeAndReplay();
    if (failures == 0) std::puts("broker firmware host tests passed");
    return failures == 0 ? 0 : 1;
}
