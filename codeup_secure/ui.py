"""Existing bilingual terminal selection UI."""
import os
import sys

def select_option(prompt_text: str, choices: list[tuple[str, str]], selected: int = 0) -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(prompt_text)
        for index, (_, label) in enumerate(choices, 1):
            print(f"{index}. {label}")
        answer = input(f"Choice [1-{len(choices)}]: ").strip()
        return choices[int(answer) - 1][0] if answer.isdigit() and 1 <= int(answer) <= len(choices) else choices[selected][0]

    def render(redraw: bool = False) -> None:
        if redraw:
            sys.stdout.write(f"\x1b[{len(choices)}A")
        for index, (_, label) in enumerate(choices):
            marker = ">" if index == selected else " "
            sys.stdout.write(f"\x1b[2K{marker} {label}\n")
        sys.stdout.flush()

    print(f"{prompt_text} (↑/↓, Enter)")
    render()
    if os.name == "nt":
        import msvcrt
        while True:
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                arrow = msvcrt.getwch()
                selected = (selected - 1) % len(choices) if arrow == "H" else (selected + 1) % len(choices) if arrow == "P" else selected
            elif key in ("\r", "\n"):
                sys.stdout.write("\n")
                return choices[selected][0]
            elif key == "\x03":
                raise KeyboardInterrupt
            else:
                continue
            render(redraw=True)

    import select, termios, tty
    fd = sys.stdin.fileno()
    old_terminal = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            key = os.read(fd, 1)
            if key == b"\x1b" and select.select([fd], [], [], 0.1)[0]:
                sequence = os.read(fd, 2)
                if sequence in (b"[A", b"OA"):
                    selected = (selected - 1) % len(choices)
                elif sequence in (b"[B", b"OB"):
                    selected = (selected + 1) % len(choices)
                else:
                    continue
            elif key in (b"\r", b"\n"):
                sys.stdout.write("\n")
                return choices[selected][0]
            elif key == b"\x03":
                raise KeyboardInterrupt
            else:
                continue
            render(redraw=True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_terminal)
