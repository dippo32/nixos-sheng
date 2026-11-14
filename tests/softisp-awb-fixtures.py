#!/usr/bin/env python3
"""Exercise libcamera's actual patched line-statistics macros.

Pass the path to an already patched libcamera 0.7.2 source tree. Requires a
C++ compiler in PATH (or set CXX). This does not simulate a camera or test IPA.
"""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]) / "src/libcamera/software_isp/swstats_cpu.cpp"
text = source.read_text(encoding="utf-8")
start = text.index("static constexpr unsigned int kSaturationThreshold")
end = text.index("void SwStatsCpu::statsBGGR8Line0", start)
macros = text[start:end]

harness = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <numeric>
#include <vector>
struct RGB {
    uint64_t values[3] = {};
    uint64_t &r() { return values[0]; }
    uint64_t &g() { return values[1]; }
    uint64_t &b() { return values[2]; }
};
struct SwIspStats {
    static constexpr unsigned int kYHistogramSize = 256;
    RGB sum_;
    uint64_t numPixels_ = 0;
    std::array<unsigned int, kYHistogramSize> yHistogram = {};
};
'''+macros+r'''
using Pixel = std::array<unsigned int, 3>;
SwIspStats sample(const std::vector<Pixel> &pixels, unsigned int div) {
    SwIspStats stats;
    SWSTATS_START_LINE_STATS(unsigned int)
    g2 = 0; (void)g2;
    for (const auto &pixel : pixels) {
        r = pixel[0]; g = pixel[1]; b = pixel[2];
        SWSTATS_ACCUMULATE_LINE_STATS(div)
    }
    SWSTATS_FINISH_LINE_STATS()
    return stats;
}
unsigned int hist(const SwIspStats &stats) {
    return std::accumulate(stats.yHistogram.begin(), stats.yHistogram.end(), 0u);
}
int main() {
    auto normal = sample({{10,20,30}, {40,50,60}}, 1);
    assert(normal.numPixels_ == 2 && hist(normal) == 2);
    assert(normal.sum_.r() == 50 && normal.sum_.g() == 70 && normal.sum_.b() == 90);
    auto threshold = sample({{242,5,6}, {243,5,6}, {5,243,6}, {5,6,243}}, 1);
    assert(threshold.numPixels_ == 1 && threshold.sum_.r() == 242 && hist(threshold) == 4);
    auto saturated = sample({{255,0,0}, {0,255,0}, {0,0,255}}, 1);
    assert(saturated.numPixels_ == 0 && saturated.sum_.r() == 0 && hist(saturated) == 3);
    auto tenbit = sample({{971,40,80}, {972,40,80}}, 4);
    assert(tenbit.numPixels_ == 1 && tenbit.sum_.r() == 971 && hist(tenbit) == 2);
    auto twelvebit = sample({{3887,40,80}, {3888,40,80}}, 16);
    assert(twelvebit.numPixels_ == 1 && twelvebit.sum_.r() == 3887 && hist(twelvebit) == 2);
}
'''
with tempfile.TemporaryDirectory() as directory:
    cpp = Path(directory) / "fixtures.cpp"
    binary = Path(directory) / "fixtures"
    cpp.write_text(harness, encoding="utf-8")
    command = shlex.split(os.environ.get("CXX", "c++"))
    subprocess.run(command + ["-std=c++17", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("SoftISP AWB line-statistics fixtures passed")
