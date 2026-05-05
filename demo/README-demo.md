# Recording the fbrain demo

## Requirements

```bash
brew install asciinema   # terminal recorder
brew install agg          # converts .cast to GIF (or use asciinema's svg-term)
```

## Record

```bash
asciinema rec demo/icontext-demo.cast --command "bash demo/demo.sh" --cols 72 --rows 24
```

## Preview

```bash
asciinema play demo/icontext-demo.cast
```

## Convert to GIF

```bash
agg demo/icontext-demo.cast demo/icontext-demo.gif --font-size 14 --theme monokai
```

## Embed in README

```markdown
![fbrain demo](demo/icontext-demo.gif)
```
