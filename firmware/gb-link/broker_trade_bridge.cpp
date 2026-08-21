// SPDX-License-Identifier: GPL-3.0-or-later
#include "broker_trade_bridge.hpp"

#include "../../src/layers/transport.hpp" // path after copying into upstream src/broker/

#include <algorithm>

namespace tradebroker {
namespace {

std::array<uint8_t, 32> sha256Placeholder(std::span<const uint8_t> bytes) {
    // INTEGRATION BLOCKER: bind to the Zephyr/mbedTLS SHA-256 enabled by the final
    // upstream configuration. Returning zeros would be unsafe, so compilation is
    // intentionally stopped until that binding is supplied and tested.
    static_assert(sizeof(bytes) == 0, "Implement Zephyr SHA-256 binding before firmware use");
}

} // namespace

TradeBridge::TradeBridge()
    : m_codec(onFrame, this, sendChunk, this) {}

TradeBridge& TradeBridge::instance() {
    static TradeBridge bridge;
    return bridge;
}

void TradeBridge::receiveData(std::span<const uint8_t> bytes, void* context) {
    static_cast<TradeBridge*>(context)->m_codec.feed(bytes);
}

bool TradeBridge::sendChunk(void*, std::span<const uint8_t> chunk) {
    return Transport::sendData(chunk);
}

void TradeBridge::onFrame(void* context, const ParsedFrame& frame) {
    static_cast<TradeBridge*>(context)->handle(frame);
}

void TradeBridge::handle(const ParsedFrame& frame) {
    if (frame.type == Message::hello) {
        m_codec.setTransaction(frame.transactionId);
        m_codec.send(Message::hello, std::span<const uint8_t>{});
        return;
    }
    if (frame.type == Message::getCapabilities) {
        constexpr std::array<uint8_t, 4> caps{0x3f, 0, 0, 0};
        m_codec.send(Message::capabilities, caps);
        return;
    }
    if (frame.type == Message::setOfferMon) {
        if (frame.payload.size() != 101 || frame.payload[0] > 5) return sendError(1);
        m_offerSlot = frame.payload[0];
        std::copy(frame.payload.begin() + 1, frame.payload.end(), m_offer.begin());
        m_offerReady = true;
        const auto hash = sha256Placeholder(m_offer);
        std::array<uint8_t, 33> ack{};
        ack[0] = m_offerSlot;
        std::copy(hash.begin(), hash.end(), ack.begin() + 1);
        m_codec.send(Message::offerReady, ack);
        return;
    }
    if (frame.type == Message::abortIfSafe) {
        // Integration must consult the current TradeConnection commit phase.
        return sendError(2);
    }
    sendError(3);
}

void TradeBridge::sessionStarted() {
    m_codec.send(Message::tradeSessionStarted);
}

void TradeBridge::partnerPartyReady(std::span<const uint8_t, 600> party) {
    m_codec.send(Message::partnerParty, party);
}

uint8_t TradeBridge::select(std::span<const uint8_t, 600> party, uint8_t partnerSlot) {
    if (!m_offerReady || partnerSlot > 5) {
        sendError(4);
        return 0;
    }
    m_partnerSlot = partnerSlot;
    std::copy(
        party.begin() + static_cast<size_t>(partnerSlot) * 100,
        party.begin() + static_cast<size_t>(partnerSlot + 1) * 100,
        m_selected.begin());
    const std::array<uint8_t, 1> slot{partnerSlot};
    m_codec.send(Message::partnerSelectedSlot, slot);
    m_codec.send(Message::partnerSelectedMon, m_selected);
    return m_offerSlot;
}

void TradeBridge::committed() {
    const auto offerHash = sha256Placeholder(m_offer);
    const auto selectedHash = sha256Placeholder(m_selected);
    std::array<uint8_t, 64> payload{};
    std::copy(offerHash.begin(), offerHash.end(), payload.begin());
    std::copy(selectedHash.begin(), selectedHash.end(), payload.begin() + 32);
    m_codec.send(Message::tradeCommitted, payload);
}

void TradeBridge::linkClosed() {
    constexpr std::array<uint8_t, 1> ok{0};
    m_codec.send(Message::tradeLinkClosed, ok);
}

void TradeBridge::sendError(uint16_t code) {
    const std::array<uint8_t, 2> payload{
        static_cast<uint8_t>(code & 0xff), static_cast<uint8_t>(code >> 8)};
    m_codec.send(Message::error, payload);
}

} // namespace tradebroker

