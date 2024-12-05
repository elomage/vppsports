#include "pico/stdlib.h"

#include <stdio.h>

#include "ff.h"

#include "helper_funcs.h"
#include "env.h"

static bool printBlocked = false;

void fatalError(std::string errorMessage) {
	while (true) {
		logError(std::string("FATAL: " + errorMessage).c_str());
		sleep_ms(5000);
	}
}

void notImplemented() { fatalError("Not implemented!"); }

void setPrintBlock(bool block) { printBlocked = block; }

#define _LOGGER_LOG va_list args; va_start(args, format); vprintf(format, args); va_end(args); printf("\n"); fflush(stdout);
#if defined(VPP_DEBUG) && defined(VPP_LOG_ERR)
void logError(const char *format, ...) {
	if (printBlocked) return;
	printf("[ERROR]: ");
	_LOGGER_LOG;
}
#else
void logError(const char *format, ...) {}
#endif

#if defined(VPP_DEBUG) && defined(VPP_LOG_WARN)
void logWarning(const char *format, ...) {
	if (printBlocked) return;
	printf("[WARN]:  ");
	_LOGGER_LOG;
}
#else
void logWarning(const char *format, ...) {}
#endif

#if defined(VPP_DEBUG) && defined(VPP_LOG_INFO)
void logInfo(const char *format, ...) {
	if (printBlocked) return;
	printf("[INFO]:  ");
	_LOGGER_LOG;
}
#else
void logInfo(const char *format, ...) {}
#endif


bool recursivelyDeleteIfExists(const TCHAR *path) {
	FILINFO fileInfo;
	if (f_stat(path, &fileInfo) != FR_OK)
		return true;

	if (fileInfo.fattrib == AM_DIR) {
		DIR dirObj;
		if (f_opendir(&dirObj, path) != FR_OK)
			return false;
		for (FRESULT result = f_findfirst(&dirObj, &fileInfo, path, "*"); result == FR_OK && fileInfo.fname != ""; result = f_findnext(&dirObj, &fileInfo)) {
			TCHAR currFilePath[FF_LFN_BUF + 1];
			snprintf(currFilePath, FF_LFN_BUF + 1, "%s/%s", path, fileInfo.fname);
			if (!recursivelyDeleteIfExists(currFilePath))
				return false;
		}
		if (f_closedir(&dirObj) != FR_OK)
			return false;
		return f_unlink(path) == FR_OK;
	} else return f_unlink(path) == FR_OK;
	return false;
}

