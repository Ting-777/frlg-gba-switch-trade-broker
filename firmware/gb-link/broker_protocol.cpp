// SPDX-License-Identifier: GPL-3.0-or-later
#include "broker_protocol.hpp"

#include <algorithm>
#include <cstring>

namespace tradebroker {
namespace {

uint16_t read16(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}

uint32_t read32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}

void write16(uint8_t* p, uint16_t value) {
    p[0] = value & 0xff;
    p[1] = value >> 8;
}

void write32(uint8_t* p, uint32_t value) {
    p[0] = value & 0xff;
    p[1] = (value >> 8) & 0xff;
    p[2] = (value >> 16) & 0xff;
    p[3] = (value >> 24) & 0xff;
}

} // namespace

uint32_t crc32(std::span<const uint8_t> bytes) {
    uint32_t crc = 0xffffffffu;
    for (uint8_t byte : bytes) {
        crc ^= byte;
        for (unsigned bit = 0; bit < 8; ++bit) {
            const uint32_t mask = -(crc & 1u);
            crc = (crc >> 1) ^ (0xedb88320u & mask);
        }
    }
    return ~crc;
}

Codec::Codec(ReceiveFn receive, void* receiveContext, SendChunkFn send, void* sendContext)
    : m_receive(receive), m_receiveContext(receiveContext), m_send(send), m_sendContext(sendContext) {}

void Codec::setTransaction(std::span<const uint8_t, 16> transactionId) {
    std::copy(transactionId.begin(), transactionId.end(), m_transactionId.begin());
    m_sendSequence = 0;
    m_lastReceivedSequence = 0;
}

void Codec::feed(std::span<const uint8_t> bytes) {
    if (bytes.size() > m_rx.size() - m_rxSize) {
        m_rxSize = 0; // fail closed and resynchronize; never partially apply an oversized command
        return;
    }
    std::copy(bytes.begin(), bytes.end(), m_rx.begin() + m_rxSize);
    m_rxSize += bytes.size();
    consume();
}

void Codec::consume() {
    while (m_rxSize >= magic.size()) {
        if (!matchesMagic()) {
            discardPrefix(1);
            continue;
        }
        if (m_rxSize < headerSize) return;
        const uint8_t frameVersion = m_rx[4];
        const uint16_t flags = read16(&m_rx[6]);
        const uint32_t payloadSize = read32(&m_rx[8]);
        if (frameVersion != version || flags != 0 || payloadSize > maxPayload) {
            discardPrefix(magic.size());
            continue;
        }
        const size_t frameSize = headerSize + payloadSize + crcSize;
        if (m_rxSize < frameSize) return;
        const uint32_t expected = read32(&m_rx[headerSize + payloadSize]);
        if (crc32(std::span<const uint8_t>(m_rx.data(), headerSize + payloadSize)) != expected) {
            discardPrefix(magic.size());
            continue;
        }
        const uint32_t sequence = read32(&m_rx[28]);
        const bool sameTransaction = std::equal(
            m_transactionId.begin(), m_transactionId.end(), m_rx.begin() + 12);
        if (!sameTransaction || sequence <= m_lastReceivedSequence) {
            discardPrefix(frameSize); // duplicate commands are never applied twice
            continue;
        }
        m_lastReceivedSequence = sequence;
        ParsedFrame frame{
            static_cast<Message>(m_rx[5]),
            {},
            sequence,
            std::span<const uint8_t>(m_rx.data() + headerSize, payloadSize),
        };
        std::copy(m_rx.begin() + 12, m_rx.begin() + 28, frame.transactionId.begin());
        m_receive(m_receiveContext, frame);
        discardPrefix(frameSize);
    }
}

bool Codec::send(Message type, std::span<const uint8_t> payload) {
    if (payload.size() > maxPayload) return false;
    std::copy(magic.begin(), magic.end(), m_tx.begin());
    m_tx[4] = version;
    m_tx[5] = static_cast<uint8_t>(type);
    write16(&m_tx[6], 0);
    write32(&m_tx[8], payload.size());
    std::copy(m_transactionId.begin(), m_transactionId.end(), m_tx.begin() + 12);
    write32(&m_tx[28], ++m_sendSequence);
    std::copy(payload.begin(), payload.end(), m_tx.begin() + headerSize);
    const size_t bodySize = headerSize + payload.size();
    write32(&m_tx[bodySize], crc32(std::span<const uint8_t>(m_tx.data(), bodySize)));
    const size_t total = bodySize + crcSize;
    for (size_t offset = 0; offset < total; offset += 64) {
        const size_t count = std::min<size_t>(64, total - offset);
        if (!m_send(m_sendContext, std::span<const uint8_t>(m_tx.data() + offset, count))) return false;
    }
    return true;
}

bool Codec::matchesMagic() const {
    return std::equal(magic.begin(), magic.end(), m_rx.begin());
}

void Codec::discardPrefix(size_t count) {
    std::move(m_rx.begin() + count, m_rx.begin() + m_rxSize, m_rx.begin());
    m_rxSize -= count;
}

} // namespace tradebroker

