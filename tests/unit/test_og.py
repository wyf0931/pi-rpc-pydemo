from app.og import render_social_metadata


def test_render_social_metadata_replaces_title_and_escapes_attributes():
    template = "<title>Default</title><!-- OMA:OG:START --><!-- OMA:OG:END -->"

    rendered = render_social_metadata(
        template,
        title='A <shared> "chat"',
        description="A & useful preview",
        canonical_url="https://example.test/share/token?q=1&x=2",
        image_url="https://example.test/static/oma-logo-transparent.png",
    )

    assert "<title>A &lt;shared&gt; &quot;chat&quot;</title>" in rendered
    assert 'property="og:description" content="A &amp; useful preview"' in rendered
    assert "?q=1&amp;x=2" in rendered
    assert rendered.count('property="og:title"') == 1
    assert rendered.count('name="twitter:card"') == 1
