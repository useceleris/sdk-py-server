# Conventions

Simplicity and maintainability are paramount. These rules bind every change; the surface contract lives in the specifications repository, and the JavaScript server package is the reference implementation this package mirrors.

## Descriptive names

Use full domain words: `signing_secret`, `channel_references`, `segment_id`, `credential_provider`. No abbreviations, and no single-letter names outside tight loops. A name says what the thing is; a comment exists only to state a constraint the code cannot show.

## Simplicity over abstraction

Solve the problem in front of you with the simplest structure that stays readable. No registries, factories, event frameworks, dependency-injection containers or wrapper layers. A helper earns its place only by removing real, present duplication. Prefer a function over a class, and a method on an existing class over a new class.

Signing uses only the standard library (`json`, `base64`, `hmac`, `hashlib`): no cryptography dependency.

## Maintainability

- Small modules with one responsibility; the file name states it. Modules are private (`_name.py`); `__init__.py` is the only place that re-exports, and the public surface is exactly its `__all__`.
- Import a name from the module that defines it.
- Every fixed value lives in `_constants.py`, in `SCREAMING_SNAKE_CASE`. Validation schemas and patterns stay beside the code that uses them.
- Delete code in the same change that obsoletes it.
- Every public identifier traces to a requirement or a recorded decision in the specifications repository (AUTH-01, D-001, D-003, ...).
- Errors carry stable codes and messages that name what failed, where, and which rule or limit it broke. Never interpolate received values, input values, credentials or server text. Never chain a caught exception that may hold such values: raise outside the handler, or after `contextlib.suppress`, so `__context__` stays empty.
- Validation uses Pydantic in strict mode (`validate_input`); nothing is coerced. Tagged unions use callable discriminators with fixed messages, and their variant tags are left out of error paths.
- Tests are deterministic (injected clocks), grouped by behaviour, and catch package-owned defects only. The signing vectors are generated independently of this code and shared with the reference implementation.
- Before completion, review the full diff for anything deletable without weakening behaviour or tests.

## Layout

Leave one blank line after every compound statement (`if`, `for`, `while`, `with`, `try`, `match`, `def`, `class`) before the next statement in the same block. `elif`, `else`, `except` and `finally` belong to their statement, and the end of an enclosing block needs no blank line. Code packed against the block before it is harder to read.

Every function, method and class ends with a marker comment that names it, as the first line after its body at the definition's own indentation: `# end function name` at module level or inside a function, `# end method name` inside a class, and `# end class Name`. `ruff format` puts blank lines before the marker; nothing else may come between. Ruff treats `end` as a task tag, so a marker may run past the line length.

```python
def outer(value: int) -> int:
    def inner() -> int:
        return value

    # end function inner

    return inner()


# end function outer
```

`tests/test_layout.py` enforces both rules over `src`, `tests`, `examples` and `noxfile.py`, and names the file and line of each violation. `ruff format` owns everything else about layout; `ruff check` and `mypy --strict` must pass. `uv run nox` runs all of them, and CI runs `uv run --locked nox`.
