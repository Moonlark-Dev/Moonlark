def parse_special_user_id(user_id: str) -> dict[str, str]:
    args = {}
    if not user_id.startswith("mlsid::"):
        raise ValueError("not a special ID")
    argv = user_id[7:].split(";")
    for arg in argv:
        a = arg.split("=", 1)
        args[a[0]] = a[1]
    return args