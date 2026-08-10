#include <windows.h>
#include <werapi.h>

using Install = BOOL (*)(const wchar_t*, const wchar_t*, const wchar_t*);

int wmain(int argc, wchar_t** argv) {
    if (argc != 5) return 64;
    const UINT no_ui_error_mode = SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX;
    SetErrorMode(GetErrorMode() | no_ui_error_mode);
    if (!SetThreadErrorMode(no_ui_error_mode, nullptr)) return 67;
    if (FAILED(WerSetFlags(WER_FAULT_REPORTING_NO_UI))) return 68;
    HMODULE handler = LoadLibraryW(argv[1]);
    if (!handler) return 65;
    auto install = reinterpret_cast<Install>(GetProcAddress(handler, "phasev3tj_install_crash_handler"));
    if (!install || !install(argv[2], argv[3], argv[4])) return 66;
    volatile unsigned int* invalid = nullptr;
    *invalid = 0x5633544a;
    return 0;
}
