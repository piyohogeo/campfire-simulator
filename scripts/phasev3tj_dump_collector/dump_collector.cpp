#include <windows.h>
#include <dbghelp.h>

#include <cstdint>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace {

std::string utf8(const std::wstring& value) {
    if (value.empty()) return {};
    const int bytes = WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    std::string result(static_cast<size_t>(bytes), '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.data(), static_cast<int>(value.size()), result.data(), bytes, nullptr, nullptr);
    return result;
}

std::string json_escape(const std::string& value) {
    std::ostringstream output;
    for (unsigned char ch : value) {
        switch (ch) {
            case '\\': output << "\\\\"; break;
            case '"': output << "\\\""; break;
            case '\n': output << "\\n"; break;
            case '\r': output << "\\r"; break;
            case '\t': output << "\\t"; break;
            default:
                if (ch < 0x20) {
                    const char* digits = "0123456789abcdef";
                    output << "\\u00" << digits[ch >> 4] << digits[ch & 15];
                } else {
                    output << ch;
                }
        }
    }
    return output.str();
}

std::wstring quote(const std::wstring& argument) {
    if (argument.find_first_of(L" \t\"") == std::wstring::npos) return argument;
    std::wstring result = L"\"";
    size_t slashes = 0;
    for (wchar_t ch : argument) {
        if (ch == L'\\') {
            ++slashes;
        } else if (ch == L'"') {
            result.append(slashes * 2 + 1, L'\\');
            result.push_back(L'"');
            slashes = 0;
        } else {
            result.append(slashes, L'\\');
            slashes = 0;
            result.push_back(ch);
        }
    }
    result.append(slashes * 2, L'\\');
    result.push_back(L'"');
    return result;
}

struct Result {
    bool process_created = false;
    bool access_violation_seen = false;
    bool dump_written = false;
    bool context_captured = false;
    DWORD create_error = ERROR_SUCCESS;
    DWORD dump_error = ERROR_SUCCESS;
    DWORD child_exit_code = STILL_ACTIVE;
    DWORD exception_code = 0;
    DWORD exception_thread_id = 0;
    ULONG_PTR exception_address = 0;
};

void write_metadata(const std::wstring& path, const std::wstring& target, const std::wstring& dump, const Result& result) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    output << "{\n"
           << "  \"schema\": \"campfire.phasev3tj.dump-collector.v1\",\n"
           << "  \"target\": \"" << json_escape(utf8(target)) << "\",\n"
           << "  \"dump_path\": \"" << json_escape(utf8(dump)) << "\",\n"
           << "  \"process_created\": " << (result.process_created ? "true" : "false") << ",\n"
           << "  \"access_violation_seen\": " << (result.access_violation_seen ? "true" : "false") << ",\n"
           << "  \"dump_written\": " << (result.dump_written ? "true" : "false") << ",\n"
           << "  \"context_captured\": " << (result.context_captured ? "true" : "false") << ",\n"
           << "  \"create_error\": " << result.create_error << ",\n"
           << "  \"dump_error\": " << result.dump_error << ",\n"
           << "  \"child_exit_code\": " << result.child_exit_code << ",\n"
           << "  \"child_exit_hex\": \"0x" << std::hex << std::uppercase << result.child_exit_code << std::dec << "\",\n"
           << "  \"exception_code\": " << result.exception_code << ",\n"
           << "  \"exception_hex\": \"0x" << std::hex << std::uppercase << result.exception_code << std::dec << "\",\n"
           << "  \"exception_thread_id\": " << result.exception_thread_id << ",\n"
           << "  \"exception_address\": \"0x" << std::hex << std::uppercase << result.exception_address << std::dec << "\",\n"
           << "  \"dump_type_flags\": \"MiniDumpWithFullMemory|MiniDumpWithHandleData|MiniDumpWithUnloadedModules|MiniDumpWithFullMemoryInfo|MiniDumpWithThreadInfo|MiniDumpWithTokenInformation\",\n"
           << "  \"debug_scope\": \"DEBUG_ONLY_THIS_PROCESS\",\n"
           << "  \"machine_wide_configuration_changed\": false\n"
           << "}\n";
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    std::wstring dump_path;
    std::wstring metadata_path;
    int target_index = -1;
    for (int index = 1; index < argc; ++index) {
        const std::wstring argument = argv[index];
        if (argument == L"--dump" && index + 1 < argc) dump_path = argv[++index];
        else if (argument == L"--metadata" && index + 1 < argc) metadata_path = argv[++index];
        else if (argument == L"--" && index + 1 < argc) { target_index = index + 1; break; }
    }
    if (target_index < 0 || dump_path.empty() || metadata_path.empty()) return 64;
    const std::wstring target = argv[target_index];
    std::wstring command_line;
    for (int index = target_index; index < argc; ++index) {
        if (!command_line.empty()) command_line.push_back(L' ');
        command_line += quote(argv[index]);
    }
    std::vector<wchar_t> mutable_command(command_line.begin(), command_line.end());
    mutable_command.push_back(L'\0');

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    Result result;
    if (!CreateProcessW(target.c_str(), mutable_command.data(), nullptr, nullptr, FALSE,
                        DEBUG_ONLY_THIS_PROCESS | CREATE_UNICODE_ENVIRONMENT,
                        nullptr, nullptr, &startup, &process)) {
        result.create_error = GetLastError();
        write_metadata(metadata_path, target, dump_path, result);
        return 2;
    }
    result.process_created = true;
    CloseHandle(process.hThread);

    bool active = true;
    while (active) {
        DEBUG_EVENT event{};
        if (!WaitForDebugEvent(&event, INFINITE)) break;
        DWORD continuation = DBG_CONTINUE;
        switch (event.dwDebugEventCode) {
            case CREATE_PROCESS_DEBUG_EVENT:
                if (event.u.CreateProcessInfo.hFile) CloseHandle(event.u.CreateProcessInfo.hFile);
                break;
            case LOAD_DLL_DEBUG_EVENT:
                if (event.u.LoadDll.hFile) CloseHandle(event.u.LoadDll.hFile);
                break;
            case EXCEPTION_DEBUG_EVENT: {
                const auto& exception = event.u.Exception;
                const DWORD code = exception.ExceptionRecord.ExceptionCode;
                if (code == EXCEPTION_BREAKPOINT || code == DBG_PRINTEXCEPTION_C || code == DBG_PRINTEXCEPTION_WIDE_C) {
                    continuation = DBG_CONTINUE;
                    break;
                }
                continuation = DBG_EXCEPTION_NOT_HANDLED;
                if (!exception.dwFirstChance && code == EXCEPTION_ACCESS_VIOLATION && !result.dump_written) {
                    result.access_violation_seen = true;
                    result.exception_code = code;
                    result.exception_thread_id = event.dwThreadId;
                    result.exception_address = reinterpret_cast<ULONG_PTR>(exception.ExceptionRecord.ExceptionAddress);
                    CONTEXT context{};
                    context.ContextFlags = CONTEXT_ALL;
                    HANDLE thread = OpenThread(THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, event.dwThreadId);
                    if (thread) {
                        result.context_captured = GetThreadContext(thread, &context) != FALSE;
                        CloseHandle(thread);
                    }
                    EXCEPTION_RECORD exception_record = exception.ExceptionRecord;
                    EXCEPTION_POINTERS pointers{&exception_record, &context};
                    MINIDUMP_EXCEPTION_INFORMATION exception_info{event.dwThreadId, &pointers, FALSE};
                    HANDLE dump_file = CreateFileW(dump_path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
                    if (dump_file != INVALID_HANDLE_VALUE) {
                        const auto flags = static_cast<MINIDUMP_TYPE>(
                            MiniDumpWithFullMemory | MiniDumpWithHandleData | MiniDumpWithUnloadedModules |
                            MiniDumpWithFullMemoryInfo | MiniDumpWithThreadInfo | MiniDumpWithTokenInformation);
                        result.dump_written = MiniDumpWriteDump(
                            process.hProcess, process.dwProcessId, dump_file, flags,
                            result.context_captured ? &exception_info : nullptr, nullptr, nullptr) != FALSE;
                        if (!result.dump_written) result.dump_error = GetLastError();
                        FlushFileBuffers(dump_file);
                        CloseHandle(dump_file);
                    } else {
                        result.dump_error = GetLastError();
                    }
                }
                break;
            }
            case EXIT_PROCESS_DEBUG_EVENT:
                result.child_exit_code = event.u.ExitProcess.dwExitCode;
                active = false;
                break;
            default:
                break;
        }
        ContinueDebugEvent(event.dwProcessId, event.dwThreadId, continuation);
    }
    CloseHandle(process.hProcess);
    write_metadata(metadata_path, target, dump_path, result);
    return (result.access_violation_seen && !result.dump_written) ? 3 : 0;
}
