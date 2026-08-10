#include <windows.h>
#include <dbghelp.h>

#include <cstdio>
#include <cstdlib>
#include <cwchar>
#include <string>

namespace {

const wchar_t* value_after(int argc, wchar_t** argv, const wchar_t* key) {
    for (int index = 1; index + 1 < argc; ++index) {
        if (std::wcscmp(argv[index], key) == 0) return argv[index + 1];
    }
    return nullptr;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    const wchar_t* pid_text = value_after(argc, argv, L"--pid");
    const wchar_t* thread_text = value_after(argc, argv, L"--thread");
    const wchar_t* pointers_text = value_after(argc, argv, L"--exception-pointers");
    const wchar_t* code_text = value_after(argc, argv, L"--code");
    const wchar_t* address_text = value_after(argc, argv, L"--address");
    const wchar_t* dump_path = value_after(argc, argv, L"--dump");
    const wchar_t* metadata_path = value_after(argc, argv, L"--metadata");
    if (!pid_text || !thread_text || !pointers_text || !code_text || !address_text || !dump_path || !metadata_path) return 64;
    const DWORD pid = std::wcstoul(pid_text, nullptr, 10);
    const DWORD thread_id = std::wcstoul(thread_text, nullptr, 10);
    const auto pointers_address = std::wcstoull(pointers_text, nullptr, 16);
    const DWORD code = std::wcstoul(code_text, nullptr, 16);
    const auto exception_address = std::wcstoull(address_text, nullptr, 16);
    HANDLE process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_DUP_HANDLE, FALSE, pid);
    bool dump_written = false;
    DWORD dump_error = ERROR_SUCCESS;
    if (process) {
        HANDLE file = CreateFileW(dump_path, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file != INVALID_HANDLE_VALUE) {
            MINIDUMP_EXCEPTION_INFORMATION exception_info{
                thread_id, reinterpret_cast<EXCEPTION_POINTERS*>(pointers_address), TRUE};
            const auto flags = static_cast<MINIDUMP_TYPE>(
                MiniDumpWithFullMemory | MiniDumpWithHandleData | MiniDumpWithUnloadedModules |
                MiniDumpWithFullMemoryInfo | MiniDumpWithThreadInfo | MiniDumpWithTokenInformation);
            dump_written = MiniDumpWriteDump(process, pid, file, flags, &exception_info, nullptr, nullptr) != FALSE;
            if (!dump_written) dump_error = GetLastError();
            FlushFileBuffers(file);
            CloseHandle(file);
        } else {
            dump_error = GetLastError();
        }
        CloseHandle(process);
    } else {
        dump_error = GetLastError();
    }
    char buffer[4096]{};
    const int length = std::snprintf(
        buffer, sizeof(buffer),
        "{\n"
        "  \"schema\": \"campfire.phasev3tj.out-of-process-dump-helper.v1\",\n"
        "  \"access_violation_seen\": true,\n"
        "  \"dump_written\": %s,\n"
        "  \"dump_error\": %lu,\n"
        "  \"exception_code\": %lu,\n"
        "  \"exception_hex\": \"0x%08lX\",\n"
        "  \"exception_thread_id\": %lu,\n"
        "  \"exception_address\": \"0x%llX\",\n"
        "  \"remote_exception_pointers_used\": true,\n"
        "  \"dump_type_flags\": \"MiniDumpWithFullMemory|MiniDumpWithHandleData|MiniDumpWithUnloadedModules|MiniDumpWithFullMemoryInfo|MiniDumpWithThreadInfo|MiniDumpWithTokenInformation\",\n"
        "  \"scope\": \"handler installed only in the isolated target process\",\n"
        "  \"machine_wide_configuration_changed\": false\n"
        "}\n",
        dump_written ? "true" : "false", dump_error, code, code, thread_id, exception_address);
    HANDLE metadata = CreateFileW(metadata_path, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (metadata != INVALID_HANDLE_VALUE) {
        DWORD written = 0;
        WriteFile(metadata, buffer, static_cast<DWORD>(length > 0 ? length : 0), &written, nullptr);
        FlushFileBuffers(metadata);
        CloseHandle(metadata);
    }
    return dump_written ? 0 : 2;
}
