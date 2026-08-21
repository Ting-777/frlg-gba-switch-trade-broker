CXX ?= g++
CXXFLAGS ?= -std=c++20 -Wall -Wextra -Werror -O1 -g

SOURCES = brokerProtocolTest.cpp ../../gb-link/broker_protocol.cpp ../../gb-link/sha256.cpp

all: run

brokerProtocolTest: $(SOURCES)
	$(CXX) $(CXXFLAGS) -o $@ $(SOURCES)

run: brokerProtocolTest
	./brokerProtocolTest

clean:
	rm -f brokerProtocolTest

.PHONY: all run clean
