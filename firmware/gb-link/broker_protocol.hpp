// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace tradebroker {

constexpr std::array<uint8_t, 4> magic{'F', 'G', 'B', 'R'};
constexpr uint8_t version = 1;
constexpr size_t headerSize = 32;
constexpr size_t crcSize = 4;
constexpr size_t maxPayload = 4096;
constexpr size_t maxFrame = headerSize + maxPayload + crcSize;

enum class Message : uint8_t {
    hello = 0x01,
    getCapabilities = 0x02,
    capabilities = 0x03,
    tradeSessionStarted = 0x10,
    partnerParty = 0x11,
    partnerSelectedSlot = 0x12,
    partnerSelectedMon = 0x13,
    setOfferMon = 0x20,
    offerReady = 0x21,
    tradeNegotiation = 0x22,
    tradeCommitted = 0x23,
    tradeAborted = 0x24,
    tradeLinkClosed = 0x25,
    abortIfSafe = 0x26,
    error = 0x7f,
};

struct ParsedFrame {
    Message type;
    std::array<uint8_t, 16> transactionId;
    uint32_t sequence;
    std::span<const uint8_t> payload;
};

using ReceiveFn = void (*)(void* context, const ParsedFrame& frame);
using SendChunkFn = bool (*)(void* context, std::span<const uint8_t> chunk);

uint32_t crc32(std::span<const uint8_t> bytes);

class Codec {
public:
    Codec(ReceiveFn receive, void* receiveContext, SendChunkFn send, void* sendContext);

    // Feed one or more arbitrary existing Transport data chunks.
    void feed(std::span<const uint8_t> bytes);

    // Serialize one inner FGBR frame and split it into <=64-byte Transport chunks.
    bool send(Message type, std::span<const uint8_t> payload = {});

    void setTransaction(std::span<const uint8_t, 16> transactionId);
    [[nodiscard]] uint32_t lastReceivedSequence() const { return m_lastReceivedSequence; }

private:
    void consume();
    void discardPrefix(size_t count);
    bool matchesMagic() const;

    ReceiveFn m_receive;
    void* m_receiveContext;
    SendChunkFn m_send;
    void* m_sendContext;
    std::array<uint8_t, maxFrame> m_rx{};
    size_t m_rxSize = 0;
    std::array<uint8_t, maxFrame> m_tx{};
    std::array<uint8_t, 16> m_transactionId{};
    uint32_t m_sendSequence = 0;
    uint32_t m_lastReceivedSequence = 0;
};

} // namespace tradebroker

