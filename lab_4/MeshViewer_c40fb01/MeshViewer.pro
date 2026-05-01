TEMPLATE = app
QT += opengl
QT += widgets

CONFIG += debug
CONFIG += warn_on
QMAKE_CXXFLAGS += -D__USE_XOPEN

# Inputs:
INCLUDEPATH += . ./include

LIBPATH += ./lib

HEADERS += ./*.h
SOURCES += ./*.cxx

LIBS += -lGLU
LIBS += -lOpenMeshCore -lOpenMeshTools

# Outputs:
TARGET = MeshViewer
MOC_DIR = build
OBJECTS_DIR = build
RCC_DIR = build

