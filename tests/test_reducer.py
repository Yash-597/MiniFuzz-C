from minifuzz.reducer import ddmin, remove_blocks, simplify_constants


def test_ddmin_finds_minimal_pair():
    lines = [f"line{i}" for i in range(50)]
    out = ddmin(lines, lambda ls: "line7" in ls and "line33" in ls)
    assert out == ["line7", "line33"]


def test_remove_blocks_drops_irrelevant_block():
    lines = ["int main(void) {", "    if (x) {", "        foo();", "    }", "    bar();", "}"]

    def pred(ls):
        text = "\n".join(ls)
        return text.count("{") == text.count("}") and "bar();" in text

    out = "\n".join(remove_blocks(lines, pred))
    assert "foo();" not in out and "bar();" in out


def test_simplify_constants_only_shrinks():
    out = simplify_constants(["v0 = 4294967295u;", "v1 = 0u;"], lambda ls: "v0" in ls[0])
    assert out == ["v0 = 0u;", "v1 = 0u;"]
