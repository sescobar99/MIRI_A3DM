#ifndef __MOUSE_POSITION__

#include <QtGlobal>

#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
#  define POS pos
#  define QROUND
#else
#  define POS position
#  define QROUND qRound
#endif

#define __MOUSE_POSITION__ = 1
#endif
