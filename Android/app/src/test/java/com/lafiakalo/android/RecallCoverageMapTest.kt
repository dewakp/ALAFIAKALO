package com.lafiakalo.android

import com.alafia.android.views.fda.albers
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The projection, pinned — the same four properties the web map asserts.
 *
 * The web version rendered the country UPSIDE DOWN on its first attempt: the
 * textbook Albers form puts north at a LARGER y, and y grows downward on a
 * canvas. Nothing about the code looks wrong; it is the standard formula. Three
 * renderings of one dataset should not disagree about where Missouri is, so
 * this checks the port rather than trusting it.
 */
class RecallCoverageMapTest {

    private val seattle = Pair(-122.3, 47.6)
    private val losAngeles = Pair(-118.2, 34.1)
    private val miami = Pair(-80.2, 25.8)
    private val newYork = Pair(-74.0, 40.7)
    private val portlandME = Pair(-70.3, 43.7)

    private fun x(p: Pair<Double, Double>) = albers(p.first, p.second).first
    private fun y(p: Pair<Double, Double>) = albers(p.first, p.second).second

    @Test
    fun `north is above south`() {
        assertTrue("Seattle must sit above Los Angeles", y(seattle) < y(losAngeles))
        assertTrue("New York must sit above Miami", y(newYork) < y(miami))
    }

    @Test
    fun `west is left of east`() {
        assertTrue(x(losAngeles) < x(newYork))
        assertTrue(x(newYork) < x(portlandME))
    }

    @Test
    fun `the country is wider than it is tall`() {
        val pts = listOf(seattle, losAngeles, miami, newYork, portlandME)
        val w = pts.maxOf { x(it) } - pts.minOf { x(it) }
        val h = pts.maxOf { y(it) } - pts.minOf { y(it) }
        assertTrue(w > h)
    }

    @Test
    fun `a parallel curves - a conic, not a rectangle`() {
        // A parallel is an arc centred on the cone's apex, which sits north of
        // the map, so it hangs lowest at the central meridian (-96) and rises
        // toward the edges. A plain lon-lat plot would tie.
        val centre = albers(-96.0, 49.0).second
        val edge = albers(-124.0, 49.0).second
        assertTrue("the US-Canada border must sag at the centre", centre > edge)
    }
}
