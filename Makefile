PREFIX ?= /usr/local
VERSION := 3.0

make install:
	mkdir -p $(PREFIX)/bin $(PREFIX)/util $(PREFIX)/lib
	sed 's|/src|/lib|' bin/qstat > $(PREFIX)/bin/qstat
	sed 's|/src|/lib|' util/gen_data > $(PREFIX)/util/gen_data
	cp -r src/qscache $(PREFIX)/lib/qscache
	ln -s lib/qscache/cfg $(PREFIX)/cfg
	chmod +x $(PREFIX)/bin/qstat $(PREFIX)/util/gen_data

build:
	python3 -m build

# These commands can only be run successfully by package maintainers
manual-upload: 
	python3 -m twine upload dist/*

test-upload:
	python3 -m twine upload --repository testpypi dist/*

#release: man
#	git tag v$(VERSION)
#	git push origin v$(VERSION)

clean:
	rm -rf dist build
