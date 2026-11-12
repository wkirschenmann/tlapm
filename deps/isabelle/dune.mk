#
# See https://isabelle.in.tum.de/dist/ for download files and their SHA256 sums.
#
OS_TYPE=$(patsubst CYGWIN%,Cygwin,$(shell uname))
HOST_CPU=$(shell uname -m)

ISABELLE_VSN=Isabelle2026

# Isabelle2026 ships one archive per OS and CPU (Isabelle2025's macOS
# archive held both CPUs).
ifeq ($(OS_TYPE),Linux)
ifeq ($(HOST_CPU),aarch64)
	ISABELLE_SHA256=edfb1670d8bdfa42488829ca0379c219b874a1e7548340c9951ffd2250da5a7f
	ISABELLE_ARCHIVE=$(ISABELLE_VSN)_linux_arm.tar.gz
else
	ISABELLE_SHA256=858c995b32216b3876bf395c3be843147d1f1eee404bc6c958d7534ee335e48d
	ISABELLE_ARCHIVE=$(ISABELLE_VSN)_linux.tar.gz
endif
	ISABELLE_ARCHIVE_TYPE=tgz
	ISABELLE_ARCHIVE_DIR=$(ISABELLE_VSN)
endif
ifeq ($(OS_TYPE),Darwin)
ifeq ($(HOST_CPU),arm64)
	ISABELLE_SHA256=7244e596d44ee9fbb8b988ef2990474b3385fa4a7ec1343867b224a13b6ddc28
	ISABELLE_ARCHIVE=$(ISABELLE_VSN)_macos_arm.tar.gz
else
	ISABELLE_SHA256=ac750bf2a124005109df686177405551c9c3a61ad0d1064d5958b0a27af3f079
	ISABELLE_ARCHIVE=$(ISABELLE_VSN)_macos.tar.gz
endif
	ISABELLE_ARCHIVE_TYPE=tgz
	ISABELLE_ARCHIVE_DIR=$(ISABELLE_VSN).app
endif
ifeq ($(OS_TYPE),Cygwin)
	# TODO: Fix this.  Isabelle2026 publishes no Cygwin bundle (only
	# Isabelle2026.exe); these lines still name Isabelle2025's.
	ISABELLE_SHA256=ab449a85c0f7c483027c2000889ec93b3f7df565d9d0c6902af2d666b3b58220
	ISABELLE_ARCHIVE=$(ISABELLE_VSN)_bundle_x86-cygwin.tar.gz
	ISABELLE_ARCHIVE_TYPE=tgz
	ISABELLE_ARCHIVE_DIR=$(ISABELLE_VSN)
endif

ISABELLE_URL=https://isabelle.in.tum.de/website-$(ISABELLE_VSN)/dist/$(ISABELLE_ARCHIVE)
ISABELLE_DIR=Isabelle
ISABELLE_TEST=Isabelle-test

# Some defaults, for the case if makefile is called not by the dune build system.
PROJECT_ROOT=$(if $(DUNE_SOURCEROOT),$(DUNE_SOURCEROOT),../..)
CACHE_DIR=$(PROJECT_ROOT)/_build_cache


all: $(ISABELLE_DIR) $(ISABELLE_DIR)/src/TLA+ $(ISABELLE_TEST) Isabelle-install

# Download the isabelle archive to the cache.
$(CACHE_DIR)/$(ISABELLE_ARCHIVE):
	mkdir -p $(CACHE_DIR)
	(echo "$(ISABELLE_SHA256) *$@" | shasum -a 256 -c -) || ( \
		(rm -f $@) && \
		(wget --progress=dot:giga --directory-prefix=$(CACHE_DIR) $(ISABELLE_URL)) && \
		(echo "$(ISABELLE_SHA256) *$@" | shasum -a 256 -c -) \
	)
.PHONY: $(CACHE_DIR)/$(ISABELLE_ARCHIVE) # Have to double-check the checksum.

# Take the Isabelle archive from the cache.
$(ISABELLE_ARCHIVE): $(CACHE_DIR)/$(ISABELLE_ARCHIVE)
	rm -f $@
	ln -s $< $@

# Extract the isabelle archive and remove the symlinks.
# TODO: This is is a workaround to eliminate symlinks to directories
# 		until https://github.com/ocaml/dune/issues/7831 is resolved.
$(ISABELLE_DIR) $(ISABELLE_TEST): $(ISABELLE_ARCHIVE)
	rm -rf $(ISABELLE_DIR)
ifeq ($(ISABELLE_ARCHIVE_TYPE),tgz)
	tar -xzf $<
	mv $(ISABELLE_ARCHIVE_DIR) $(ISABELLE_DIR)
endif
	cd $(ISABELLE_DIR) && rm -rf ./contrib/e-*/src/lib/
ifeq ($(OS_TYPE),Darwin)
	cd $(ISABELLE_DIR) && for d in contrib/jdk-*/*-darwin; do \
		( cd $$d && (find . -type link | xargs rm) \
			&& mv zulu-*.jdk/Contents/Home/* ./ ) || exit 1; \
	done
endif
	cp -r $(ISABELLE_DIR) $(ISABELLE_TEST)

# Build the TLA+ theory.
.PRECIOUS: $(ISABELLE_DIR)/src/TLA+
$(ISABELLE_DIR)/src/TLA+: $(ISABELLE_DIR)
	cd $(ISABELLE_DIR) \
		&& rm -rf contrib/ProofGeneral* doc heaps/*/HOL contrib/vscodium* contrib/vscode* \
		&& awk '/^((contrib\/(vscode_extension|vscodium))|(src\/Tools\/Demo))/{ print "#rm at TLA# " $$0; next } END { print "src/TLA+" } { print }' etc/components > etc/components.tmp \
		&& rm etc/components && mv etc/components.tmp etc/components
	mkdir -p $(ISABELLE_DIR)/src/TLA+ \
		&& cp -a ../../isabelle/* $(ISABELLE_DIR)/src/TLA+/ \
		&& chmod -R u+w $(ISABELLE_DIR)/src/TLA+/ \
		&& make -C $(ISABELLE_DIR)/src/TLA+/ clean
	cd $(ISABELLE_DIR)/ \
		&& ./bin/isabelle build -o system_heaps -o document=false -b -v -d src/Pure Pure \
		&& ./bin/isabelle build -o system_heaps -o document=false -b -c -v -d src/TLA+ TLA+ \
		&& rm -rf ./heaps/polyml-*/log/*

# Bake the options "isabelle ML_process -l TLA+" would otherwise reload via
# the JVM on every invocation into a small extra heap layer on top of TLA+,
# so Params.isabelle (src/params.ml) can just load that layer instead.
# The layer also defines use_thy (tlapm_use_thy.ML), which Params.isabelle
# calls and Isabelle2026 no longer provides.
# etc/ml_paths.txt records ML_HOME (Poly/ML's directory) and the heaps'
# directory, both of which name Poly/ML's version and platform.  Since
# Isabelle2026, "isabelle env" and "isabelle getenv" no longer define
# ML_HOME and ML_IDENTIFIER: the ML process itself reports them.
$(ISABELLE_DIR)/etc/ml_paths.txt: $(ISABELLE_DIR)/src/TLA+ tlapm_use_thy.ML
	rm -f $@ $@.tmp
	cd $(ISABELLE_DIR) \
		&& ./bin/isabelle ML_process -d src/TLA+ -l TLA+ \
			-f ../tlapm_use_thy.ML \
			-e 'let val heaps = "heaps/" ^ getenv "ML_SYSTEM" ^ "_" ^ ML_System.platform in File.write (Path.explode "'"$$PWD"'/etc/ml_paths.txt.tmp") (getenv "ML_HOME" ^ "\n" ^ heaps ^ "\n"); ML_Heap.save_child (heaps ^ "/Options") end;'
	ML_HOME=$$(sed -n 1p $@.tmp) && HEAPS=$$(sed -n 2p $@.tmp) \
		&& test -n "$$ML_HOME" && test -d "$$ML_HOME" \
		&& test -f "$(ISABELLE_DIR)/$$HEAPS/Options" \
		&& mv $@.tmp $@

# Assemble the minimal subset of the built distribution that tlapm actually
# needs at runtime.
Isabelle-install: $(ISABELLE_DIR)/etc/ml_paths.txt
	rm -rf $@
	mkdir -p $@/poly $@/etc $@/heaps
	cp -a $(ISABELLE_DIR)/etc/ISABELLE_IDENTIFIER $@/etc/ISABELLE_IDENTIFIER
	ML_HOME=$$(sed -n 1p $(ISABELLE_DIR)/etc/ml_paths.txt) \
		&& HEAPS=$(ISABELLE_DIR)/$$(sed -n 2p $(ISABELLE_DIR)/etc/ml_paths.txt) \
		&& test -n "$$ML_HOME" && test -d "$$ML_HOME" \
		&& cp -a "$$ML_HOME"/. $@/poly/ \
		&& cp -a $$HEAPS/Pure $@/heaps/Pure \
		&& cp -a $$HEAPS/TLA+ $@/heaps/TLA+ \
		&& cp -a $$HEAPS/Options $@/heaps/Options

clean:
	rm -rf $(ISABELLE_ARCHIVE) $(ISABELLE_DIR) $(ISABELLE_TEST) Isabelle-install

.PHONY: all clean
