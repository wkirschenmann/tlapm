OS_TYPE=$(patsubst CYGWIN%,Cygwin,$(shell uname))

# LS4 1.1: the tag ls4_v1.1 (0293895) and the commit after it (530d67a),
# which compiles with current C++ compilers.  Since 1.0 it fixes the leap
# index computation (c5e907e).
LS4_VERS=530d67a8dc838c849b3406eda638c1b0c6a59795
LS4_URL_PREFIX=https://github.com/quickbeam123/ls4/archive
LS4_BASE_NAME=ls4-$(LS4_VERS)

ifeq ($(OS_TYPE),Linux)
	LS4_EXEC=ls4
endif
ifeq ($(OS_TYPE),Darwin)
	LS4_EXEC=ls4
endif
ifeq ($(OS_TYPE),Cygwin)
	LS4_EXEC=ls4.exe
endif

all: ls4

$(LS4_VERS).zip:
	wget --progress=dot:giga $(LS4_URL_PREFIX)/$@

$(LS4_BASE_NAME): $(LS4_VERS).zip
	rm -rf $@
	unzip $<
	touch $@ # To avoid rebuilds.
	( set -x && patch -d $@ -p1 <ls4.patch )
	cd $(LS4_BASE_NAME)/core && cc -c aiger.c
	make -C $(LS4_BASE_NAME)/core

ls4: $(LS4_BASE_NAME)
	cp -f $</core/$(LS4_EXEC) $@

clean:
	rm -rf ls4 $(LS4_BASE_NAME) $(LS4_VERS).zip

.PHONY: all clean
