// Adapted from RantanPlan (https://github.com/udg-lai/ICAPS26-Mutex-On-Demand-SMT).
#include "memory_tracker.hpp"
#include <fstream>
#include <sstream>

// Platform-specific includes
#ifdef __APPLE__
#include <mach/mach.h>
#include <mach/task.h>
#elif __linux__
#include <unistd.h>
#include <fstream>
#endif

namespace bp {

MemoryTracker& MemoryTracker::instance() {
    static MemoryTracker instance;
    return instance;
}

double MemoryTracker::get_current_memory_mb() {
    return read_rss_memory_mb();
}

double MemoryTracker::read_rss_memory_mb() {
#ifdef __APPLE__
    // macOS implementation using task_info
    struct mach_task_basic_info info;
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    
    kern_return_t kr = task_info(mach_task_self(), MACH_TASK_BASIC_INFO, 
                                reinterpret_cast<task_info_t>(&info), &count);
    if (kr == KERN_SUCCESS) {
        // resident_size is in bytes, convert to MB
        return static_cast<double>(info.resident_size) / (1024.0 * 1024.0);
    }
    
#elif __linux__
    // Linux implementation using /proc/self/status
    std::ifstream status_file("/proc/self/status");
    std::string line;
    
    while (std::getline(status_file, line)) {
        if (line.find("VmRSS:") == 0) {
            std::istringstream iss(line);
            std::string label;
            long rss_kb;
            std::string unit;
            
            if (iss >> label >> rss_kb >> unit) {
                // VmRSS is typically in kB, convert to MB
                return static_cast<double>(rss_kb) / 1024.0;
            }
            break;
        }
    }
    
#endif
    
    // Fallback: unable to read memory on this platform
    return 0.0;
}

} // namespace bp