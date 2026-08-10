#include <windows.h>

#include <cwchar>

namespace {

wchar_t g_helper_path[32768]{};
wchar_t g_dump_path[32768]{};
wchar_t g_metadata_path[32768]{};
LPTOP_LEVEL_EXCEPTION_FILTER g_previous_filter = nullptr;
volatile LONG g_dump_started = 0;

LONG WINAPI crash_filter(EXCEPTION_POINTERS* pointers) {
    const DWORD code = pointers && pointers->ExceptionRecord ? pointers->ExceptionRecord->ExceptionCode : 0;
    if (code == EXCEPTION_ACCESS_VIOLATION && InterlockedCompareExchange(&g_dump_started, 1, 0) == 0) {
        wchar_t final_command[65536]{};
        swprintf_s(final_command, L"\"%s\" --pid %lu --thread %lu --exception-pointers %llX --code %08lX --address %llX --dump \"%s\" --metadata \"%s\"",
                   g_helper_path, GetCurrentProcessId(), GetCurrentThreadId(),
                   reinterpret_cast<unsigned long long>(pointers), code,
                   reinterpret_cast<unsigned long long>(pointers->ExceptionRecord->ExceptionAddress),
                   g_dump_path, g_metadata_path);
        STARTUPINFOW startup{};
        startup.cb = sizeof(startup);
        PROCESS_INFORMATION process{};
        if (CreateProcessW(g_helper_path, final_command, nullptr, nullptr, FALSE,
                           CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
                           nullptr, nullptr, &startup, &process)) {
            CloseHandle(process.hThread);
            WaitForSingleObject(process.hProcess, 120000);
            CloseHandle(process.hProcess);
        }
    }
    if (g_previous_filter && g_previous_filter != crash_filter) return g_previous_filter(pointers);
    return EXCEPTION_CONTINUE_SEARCH;
}

}  // namespace

extern "C" __declspec(dllexport) BOOL phasev3tj_install_crash_handler(
    const wchar_t* helper_path, const wchar_t* dump_path, const wchar_t* metadata_path) {
    if (!helper_path || !dump_path || !metadata_path || !*helper_path || !*dump_path || !*metadata_path) return FALSE;
    if (wcsncpy_s(g_helper_path, helper_path, _TRUNCATE) != 0) return FALSE;
    if (wcsncpy_s(g_dump_path, dump_path, _TRUNCATE) != 0) return FALSE;
    if (wcsncpy_s(g_metadata_path, metadata_path, _TRUNCATE) != 0) return FALSE;
    InterlockedExchange(&g_dump_started, 0);
    g_previous_filter = SetUnhandledExceptionFilter(crash_filter);
    return TRUE;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) {
    return TRUE;
}
