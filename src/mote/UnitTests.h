#ifndef __UNITTESTS_H_
#define __UNITTESTS_H_

#include <string>

class Assertion {
	std::string _message = "", _testName = "", _expected = "", _actual = "";
	int _line = -1;
	bool _assertionFailed = false;

	static std::string convertBoolToString(bool val);

public:
	Assertion(){}
	Assertion(std::string message, std::string testName, int line, std::string expected, std::string actual) : _message(message), _testName(testName), _expected(expected), _actual(actual), _line(line), _assertionFailed(expected != actual) {}
	template <typename T, typename = typename std::enable_if<std::is_arithmetic<T>::value, T>::type>//Only template numeric types
	Assertion(std::string message, std::string testName, long long line, T expected, T actual) : Assertion(message, testName, line, std::to_string(expected), std::to_string(actual)) {}
	Assertion(std::string message, std::string testName, long long line, bool expected, bool actual) : Assertion(message, testName, line, convertBoolToString(expected), convertBoolToString(actual)) {}

	operator std::string() const;
	bool TestFailed() const;
};

bool runUnitTests();

#endif

