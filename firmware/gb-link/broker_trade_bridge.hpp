// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "broker_protocol.hpp"

#include <array>
#include <cstdint>
#include <span>

namespace tradebroker {

class TradeBridge {
public:
    TradeBridge();

    static TradeBridge& instance();
    static void receiveData(std::span<const uint8_t> bytes, void* context);

    void sessionStarted();
    void partnerPartyReady(std::span<const uint8_t, 600> party);
    [[nodiscard]] uint8_t select(std::span<const uint8_t, 600> party, uint8_t partnerSlot);
    void committed();
    void linkClosed();

    [[nodiscard]] bool offerReady() const { return m_offerReady; }
    [[nodiscard]] uint8_t offerSlot() const { return m_offerSlot; }
    [[nodiscard]] std::span<const uint8_t, 100> offer() const { return m_offer; }

private:
    static void onFrame(void* context, const ParsedFrame& frame);
    static bool sendChunk(void* context, std::span<const uint8_t> chunk);
    void handle(const ParsedFrame& frame);
    void sendError(uint16_t code);

    Codec m_codec;
    std::array<uint8_t, 100> m_offer{};
    std::array<uint8_t, 100> m_selected{};
    uint8_t m_offerSlot = 0;
    uint8_t m_partnerSlot = 0;
    bool m_offerReady = false;
};

} // namespace tradebroker

