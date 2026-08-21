// SPDX-License-Identifier: GPL-3.0-or-later
#include "broker_trade_bridge.hpp"
#include "sha256.hpp"

#include "../layers/transport.hpp"
#include "../payloads/pokemon.hpp"

#include <algorithm>

namespace tradebroker {
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
    if (frame.replayed) {
        if (frame.sequence == m_cachedCommandSequence) {
            m_codec.send(
                m_cachedResponseType,
                std::span<const uint8_t>(m_cachedResponse.data(), m_cachedResponseSize));
        }
        return;
    }
    if (frame.type == Message::hello) {
        reply(frame, Message::hello);
        return;
    }
    if (frame.type == Message::getCapabilities) {
        constexpr std::array<uint8_t, 4> caps{0x3f, 0, 0, 0};
        reply(frame, Message::capabilities, caps);
        return;
    }
    if (frame.type == Message::setOfferMon) {
        if (frame.payload.size() != 101 || frame.payload[0] > 5) return replyError(frame, 1);
        m_offerSlot = frame.payload[0];
        std::copy(frame.payload.begin() + 1, frame.payload.end(), m_offer.begin());
        party::setPartySlot(m_offerSlot, m_offer);
        m_offerReady = true;
        const auto hash = sha256(m_offer);
        std::array<uint8_t, 33> ack{};
        ack[0] = m_offerSlot;
        std::copy(hash.begin(), hash.end(), ack.begin() + 1);
        reply(frame, Message::offerReady, ack);
        return;
    }
    if (frame.type == Message::abortIfSafe) {
        if (m_phase == Phase::idle || m_phase == Phase::negotiating) {
            m_phase = Phase::aborted;
            m_offerReady = false;
            return reply(frame, Message::tradeAborted);
        }
        return replyError(frame, 2);
    }
    replyError(frame, 3);
}

void TradeBridge::sessionStarted() {
    m_phase = Phase::negotiating;
    m_partyReported = false;
    m_codec.send(Message::tradeSessionStarted);
}

void TradeBridge::partnerPartyReady(std::span<const uint8_t, 600> party) {
    if (m_partyReported) return;
    m_partyReported = true;
    m_codec.send(Message::partnerParty, party);
}

uint8_t TradeBridge::select(std::span<const uint8_t, 600> party, uint8_t partnerSlot) {
    if (!m_offerReady || partnerSlot > 5) {
        sendError(4);
        return 0;
    }
    m_partnerSlot = partnerSlot;
    m_phase = Phase::selected;
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
    if (m_phase != Phase::selected) return sendError(5);
    m_phase = Phase::committed;
    const auto offerHash = sha256(m_offer);
    const auto selectedHash = sha256(m_selected);
    std::array<uint8_t, 64> payload{};
    std::copy(offerHash.begin(), offerHash.end(), payload.begin());
    std::copy(selectedHash.begin(), selectedHash.end(), payload.begin() + 32);
    m_codec.send(Message::tradeCommitted, payload);
}

void TradeBridge::linkClosed() {
    m_phase = Phase::closed;
    constexpr std::array<uint8_t, 1> ok{0};
    m_codec.send(Message::tradeLinkClosed, ok);
}

void TradeBridge::reply(
    const ParsedFrame& frame, Message type, std::span<const uint8_t> payload) {
    if (payload.size() > m_cachedResponse.size()) return sendError(6);
    m_cachedCommandSequence = frame.sequence;
    m_cachedResponseType = type;
    m_cachedResponseSize = payload.size();
    std::copy(payload.begin(), payload.end(), m_cachedResponse.begin());
    m_codec.send(type, payload);
}

void TradeBridge::replyError(const ParsedFrame& frame, uint16_t code) {
    const std::array<uint8_t, 2> payload{
        static_cast<uint8_t>(code & 0xff), static_cast<uint8_t>(code >> 8)};
    reply(frame, Message::error, payload);
}

void TradeBridge::sendError(uint16_t code) {
    const std::array<uint8_t, 2> payload{
        static_cast<uint8_t>(code & 0xff), static_cast<uint8_t>(code >> 8)};
    m_codec.send(Message::error, payload);
}

} // namespace tradebroker
