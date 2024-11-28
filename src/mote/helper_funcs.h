#ifndef __HELPER_FUNCS_H__
#define __HELPER_FUNCS_H__

#include <string>
#include <queue>
#include <stdarg.h>
#include <cstring>

#include "ff.h"

void fatalError(std::string errorMessage);
void logError(const char *format, ...);
void logWarning(const char *format, ...);
void logInfo(const char *format, ...);
void setPrintBlock(bool block);

#define TEST1 logWarning("Test 1")
#define TEST2 logWarning("Test 2")
#define TEST3 logWarning("Test 3")
#define TEST4 logWarning("Test 4")
#define TEST5 logWarning("Test 5")
#define TEST6 logWarning("Test 6")

/**
 * Recursively deletes any files and directories, if the given object exists
 *
 * @param path Path to the file/dir to be deleted
 * return Returns true, if the file/dir doesn't exist, false if an error was encountered
 */
bool recursivelyDeleteIfExists(const TCHAR *path);

template <typename T>
class LimitedQueue {//Methods implemented here because compiler freaks out when they're not (template stuff)
	std::queue<T> _queue;
	int _maxSize;
	volatile bool _accessLock = false;//Simple thread safity precaution, might not be enough

public:
	LimitedQueue(int maxSize) : _maxSize(maxSize) {}

	bool Push(T elem) {
		bool result = false;
		while (_accessLock);
		_accessLock = true;
		if (_queue.size() < _maxSize) {
			_queue.push(elem);
			result = true;
		}
		_accessLock = false;
		return result;
	}

	T Pop() {
		while (_accessLock);
		_accessLock = true;
		T temp = _queue.front();
		_queue.pop();
		_accessLock = false;
		return temp;
	}

	bool Empty() {
		while (_accessLock);
		_accessLock = true;
		bool result = _queue.empty();
		_accessLock = false;
		return result;
	}
};

template <typename T>
struct Nullable{
	bool isNull = true;
	T value;

	operator bool() { return !isNull; }
	operator T() { return value; }
	Nullable(bool isNull, T value) { this->isNull = isNull; this->value = value; }
	static size_t GetEncodedBufferSize() { return sizeof(isNull) + sizeof(value); }

	Nullable(char *buff) {
		std::memcpy(&isNull, buff, sizeof(isNull));
		std::memcpy(&value, buff + sizeof(isNull), sizeof(value));
	}

	void EncodeToBuffer(char *buff) {
		std::memcpy(buff, &isNull, sizeof(isNull));
		std::memcpy(buff + sizeof(isNull), &value, sizeof(value));
	}
};

#endif

