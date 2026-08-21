// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <array>
#include <cstdint>
#include <span>

namespace tradebroker {

[[nodiscard]] std::array<uint8_t, 32> sha256(std::span<const uint8_t> bytes);

} // namespace tradebroker
