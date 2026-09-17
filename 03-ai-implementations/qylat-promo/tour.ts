import type { Cut, Format, Step, Tour } from './src/types';

// The whole video is described here. Edit this file, run `npm run record`
// (or record:short, record:wide), then the matching render script. Nothing
// about timing or zoom coordinates is set by hand: the recorder measures each
// element it interacts with and writes the camera moves and captions into
// public/tour/<cut>-<format>/timeline.json.
//
// Scene order, on-screen text and narration follow the storyboard:
//   hook -> What's Stopping You -> Discover Your Idea -> Leap Calculator
//   -> Idea To Plan -> call to action.
//
// Two cuts from the same storyboard:
//   full   about 1:45, every tool shown being used, for YouTube and the site
//   short  under a minute, one beat per tool, for Reels, TikTok and Shorts
//
// Two formats:
//   portrait   records the phone layout at a phone viewport, renders 1080x1920
//   landscape  records the desktop layout in a browser window, renders 1920x1080

export function buildTour(cut: Cut, format: Format): Tour {
  const P = format === 'portrait';
  const S = cut === 'short';
  // Hold times: full cut first, short cut second.
  const w = (full: number, short: number) => (S ? short : full);

  // Zoom levels by purpose. `false` means the camera stays put.
  type Zoom = number | false;
  const Z: Record<'nav' | 'heading' | 'field' | 'detail', Zoom> = {
    nav: false,                    // clicking a menu item: no zoom, the page change is the point
    heading: P ? false : 1.2,      // a section heading
    field: P ? 1.15 : 1.3,         // a form field or button being used
    detail: P ? 1.25 : 1.4,        // a line worth reading closely
  };

  // The phone layout hides the nav behind a hamburger button, so open it first.
  const nav = (label: string): Step[] => [
    ...(P ? [{ action: 'click', selector: 'button[aria-label="Toggle menu"]', zoom: false, wait: w(700, 350) } as Step] : []),
    { action: 'click', selector: `header >> text="${label}" >> visible=true`, zoom: Z.nav, wait: w(2200, 1000) },
  ];

  return {
    baseUrl: process.env.BASE_URL ?? 'https://quityourlifeandtravel.com',
    cut,
    format,
    viewport: P ? { width: 390, height: 660 } : { width: 1440, height: 900 },
    pace: S ? 0.7 : 1,
    introMs: w(4000, 2200),
    outroMs: w(6000, 3500),
    scenes: [
      {
        id: 'hook',
        eyebrow: 'quityourlifeandtravel.com',
        title: 'Quit Your Life & Travel',
        subtitle: 'Your Thailand Escape Plan',
        narration: S
          ? 'Thinking about a new life in Thailand but not sure where to start? Four free tools, in order.'
          : "Thinking about making the leap, quitting the rat race, and starting a new life in Thailand, but don't know where to start? Welcome to QYLAT.",
        steps: [
          { action: 'zoom', selector: 'h1', level: P ? 1.1 : 1.15, wait: w(3200, 1800) },
          { action: 'zoomOut', wait: w(1200, 400) },
        ],
      },
      {
        id: 'whats-stopping-you',
        eyebrow: 'Tool 1 of 4',
        title: 'Step 1: The Barrier Assessment',
        subtitle: '16 Honest Questions',
        narration: S
          ? 'First, sixteen honest questions that name the one thing actually in your way.'
          : "First, figure out what's holding you back. The What's Stopping You quiz asks 16 honest questions to pinpoint whether your biggest hurdle is savings, mindset, or clarity.",
        steps: [
          ...nav("What's Stopping You"),
          ...(S ? [] : [{ action: 'scrollTo', selector: 'text=Question 1 of 16', zoom: Z.heading, wait: 2400 } as Step]),
          { action: 'click', selector: 'button:has-text("Four to nine months")', zoom: Z.field, wait: w(1600, 900) },
          ...(S ? [] : [{ action: 'click', selector: 'button:has-text("Most of it, with some disruption")', zoom: Z.field, wait: 1600 } as Step]),
          { action: 'zoomOut', wait: w(1500, 300) },
        ],
      },
      {
        id: 'discover-your-idea',
        eyebrow: 'Tool 2 of 4',
        title: 'Step 2: Discover Your Idea',
        subtitle: '10 Custom Business Ideas for Thailand',
        narration: S
          ? 'Then a five question skills match, with business ideas you could run from Thailand.'
          : 'Next, find out what business you can actually launch. Take the free Skill Assessment to get matched with 10 tailored business ideas you can start and run directly from Thailand.',
        steps: [
          ...nav('Discover Your Idea'),
          ...(S ? [] : [{ action: 'scrollTo', selector: '#discover-your-idea h2', zoom: Z.heading, wait: 1800 } as Step]),
          { action: 'click', selector: '#discover-your-idea a[href="/assessment"]', zoom: Z.field, wait: w(2200, 1100) },
          { action: 'click', selector: 'button:has-text("Writing & copywriting")', zoom: Z.field, wait: w(500, 350) },
          { action: 'click', selector: 'button:has-text("AI & automation tools")', zoom: false, wait: w(700, 700) },
          ...(S
            ? []
            : ([
                { action: 'click', selector: 'button:has-text("Next")', zoom: false, wait: 1000 },
                { action: 'click', selector: 'button:has-text("Problem-solving")', zoom: Z.field, wait: 500 },
                { action: 'click', selector: 'button:has-text("Empathy & listening")', zoom: false, wait: 1200 },
              ] as Step[])),
          { action: 'zoomOut', wait: w(1500, 300) },
        ],
      },
      {
        id: 'calculator',
        eyebrow: 'Tool 3 of 4',
        title: 'Step 3: Runway Calculator',
        subtitle: 'Know Your Numbers in Thailand',
        narration: S
          ? 'The Leap Calculator turns your savings into months of runway, on real Chiang Mai costs.'
          : 'Wondering how long your savings will last? Use the Leap Runway Calculator to map out your exact financial runway in Thailand based on real local living costs.',
        steps: [
          ...nav('Leap Calculator'),
          { action: 'type', selector: 'input[placeholder="Spendable cash"]', text: '25000', zoom: Z.field, wait: w(1400, 600) },
          ...(S ? [] : [{ action: 'scrollTo', selector: 'text=What Life in Chiang Mai Costs', zoom: Z.heading, wait: 2400 } as Step]),
          { action: 'scrollTo', selector: 'text=Net cash for your runway', zoom: Z.detail, wait: w(2600, 1500) },
          { action: 'zoomOut', wait: w(1500, 300) },
        ],
      },
      {
        id: 'idea-to-plan',
        eyebrow: 'Tool 4 of 4',
        title: 'Step 4: Idea To Plan',
        subtitle: 'Complete Business Plan for $25',
        narration: S
          ? 'And when you are ready, Idea To Plan turns the idea into a full business plan, from $25.'
          : 'Ready to make it official? The AI Business Planning tool transforms your idea into a personal roadmap, investor pitch, or bank loan application, currently available for a special $25 promo.',
        steps: [
          ...nav('Idea To Plan'),
          ...(S ? [] : [{ action: 'scrollTo', selector: '#idea-to-plan h2', zoom: Z.heading, wait: 3000 } as Step]),
          { action: 'scrollTo', selector: 'text=Plans start at $25', zoom: Z.detail, wait: w(3200, 1600) },
          { action: 'zoomOut', wait: w(1500, 300) },
        ],
      },
      {
        id: 'cta',
        eyebrow: 'quityourlifeandtravel.com',
        title: 'Visit quityourlifeandtravel.com',
        subtitle: 'Start Your Free Assessment Now',
        narration: S
          ? 'Start with the free assessment at quityourlifeandtravel.com.'
          : 'Stop waiting for the perfect moment. Head over to quityourlifeandtravel.com today and design a life that actually fits.',
        steps: [
          { action: 'goto', path: '/', wait: w(1600, 800) },
          ...(S ? [] : [{ action: 'scrollTo', selector: 'a[href="/assessment"]', zoom: Z.field, wait: 2600 } as Step]),
          { action: 'zoomOut', wait: w(800, 300) },
        ],
      },
    ],
  };
}

const CUT: Cut = process.env.CUT === 'short' ? 'short' : 'full';
const FORMAT: Format = process.env.FORMAT === 'landscape' ? 'landscape' : 'portrait';

/** The variant selected by CUT and FORMAT (defaults: full, portrait). */
export const tour: Tour = buildTour(CUT, FORMAT);
