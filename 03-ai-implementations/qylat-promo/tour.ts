import type { Format, Step, Tour } from './src/types';

// The whole video is described here. Edit this file, run `npm run record`,
// then `npm run render`. Nothing about timing or zoom coordinates is set by
// hand: the recorder measures each element it interacts with and writes the
// camera moves and captions into public/tour/timeline.json.
//
// Scene order, on-screen text and narration follow the storyboard:
//   hook -> What's Stopping You -> Discover Your Idea -> Leap Calculator
//   -> Idea To Plan -> call to action. About 90 seconds.
//
// FORMAT=portrait (default) records the site's phone layout at a phone
// viewport and renders 1080x1920. Most screens need no zoom at all there.
// FORMAT=landscape records the desktop layout in a browser window at
// 1920x1080 and uses light zooms so text stays readable.

const FORMAT: Format = process.env.FORMAT === 'landscape' ? 'landscape' : 'portrait';
const P = FORMAT === 'portrait';

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
  ...(P ? [{ action: 'click', selector: 'button[aria-label="Toggle menu"]', zoom: false, wait: 700 } as Step] : []),
  { action: 'click', selector: `header >> text="${label}" >> visible=true`, zoom: Z.nav, wait: 2200 },
];

export const tour: Tour = {
  baseUrl: process.env.BASE_URL ?? 'https://quityourlifeandtravel.com',
  format: FORMAT,
  viewport: P ? { width: 390, height: 660 } : { width: 1440, height: 900 },
  introMs: 4000,
  outroMs: 6000,
  scenes: [
    {
      id: 'hook',
      eyebrow: 'quityourlifeandtravel.com',
      title: 'Quit Your Life & Travel',
      subtitle: 'Your Thailand Escape Plan',
      narration:
        "Thinking about making the leap, quitting the rat race, and starting a new life in Thailand, but don't know where to start? Welcome to QYLAT.",
      steps: [
        { action: 'zoom', selector: 'h1', level: P ? 1.1 : 1.15, wait: 3200 },
        { action: 'zoomOut', wait: 1200 },
      ],
    },
    {
      id: 'whats-stopping-you',
      eyebrow: 'Tool 1 of 4',
      title: 'Step 1: The Barrier Assessment',
      subtitle: '16 Honest Questions',
      narration:
        "First, figure out what's holding you back. The What's Stopping You quiz asks 16 honest questions to pinpoint whether your biggest hurdle is savings, mindset, or clarity.",
      steps: [
        ...nav("What's Stopping You"),
        { action: 'scrollTo', selector: 'text=Question 1 of 16', zoom: Z.heading, wait: 2400 },
        { action: 'click', selector: 'button:has-text("Four to nine months")', zoom: Z.field, wait: 1600 },
        { action: 'click', selector: 'button:has-text("Most of it, with some disruption")', zoom: Z.field, wait: 1600 },
        { action: 'zoomOut', wait: 1500 },
      ],
    },
    {
      id: 'discover-your-idea',
      eyebrow: 'Tool 2 of 4',
      title: 'Step 2: Discover Your Idea',
      subtitle: '10 Custom Business Ideas for Thailand',
      narration:
        'Next, find out what business you can actually launch. Take the free Skill Assessment to get matched with 10 tailored business ideas you can start and run directly from Thailand.',
      steps: [
        ...nav('Discover Your Idea'),
        { action: 'scrollTo', selector: '#discover-your-idea h2', zoom: Z.heading, wait: 1800 },
        { action: 'click', selector: '#discover-your-idea a[href="/assessment"]', zoom: Z.field, wait: 2200 },
        { action: 'click', selector: 'button:has-text("Writing & copywriting")', zoom: Z.field, wait: 500 },
        { action: 'click', selector: 'button:has-text("AI & automation tools")', zoom: false, wait: 700 },
        { action: 'click', selector: 'button:has-text("Next")', zoom: false, wait: 1000 },
        { action: 'click', selector: 'button:has-text("Problem-solving")', zoom: Z.field, wait: 500 },
        { action: 'click', selector: 'button:has-text("Empathy & listening")', zoom: false, wait: 1200 },
        { action: 'zoomOut', wait: 1500 },
      ],
    },
    {
      id: 'calculator',
      eyebrow: 'Tool 3 of 4',
      title: 'Step 3: Runway Calculator',
      subtitle: 'Know Your Numbers in Thailand',
      narration:
        'Wondering how long your savings will last? Use the Leap Runway Calculator to map out your exact financial runway in Thailand based on real local living costs.',
      steps: [
        ...nav('Leap Calculator'),
        { action: 'type', selector: 'input[placeholder="Spendable cash"]', text: '25000', zoom: Z.field, wait: 1400 },
        { action: 'scrollTo', selector: 'text=What Life in Chiang Mai Costs', zoom: Z.heading, wait: 2400 },
        { action: 'scrollTo', selector: 'text=Net cash for your runway', zoom: Z.detail, wait: 2600 },
        { action: 'zoomOut', wait: 1500 },
      ],
    },
    {
      id: 'idea-to-plan',
      eyebrow: 'Tool 4 of 4',
      title: 'Step 4: Idea To Plan',
      subtitle: 'Complete Business Plan for $25',
      narration:
        'Ready to make it official? The AI Business Planning tool transforms your idea into a personal roadmap, investor pitch, or bank loan application, currently available for a special $25 promo.',
      steps: [
        ...nav('Idea To Plan'),
        { action: 'scrollTo', selector: '#idea-to-plan h2', zoom: Z.heading, wait: 3000 },
        { action: 'scrollTo', selector: 'text=Plans start at $25', zoom: Z.detail, wait: 3200 },
        { action: 'zoomOut', wait: 1500 },
      ],
    },
    {
      id: 'cta',
      eyebrow: 'quityourlifeandtravel.com',
      title: 'Visit quityourlifeandtravel.com',
      subtitle: 'Start Your Free Assessment Now',
      narration:
        'Stop waiting for the perfect moment. Head over to quityourlifeandtravel.com today and design a life that actually fits.',
      steps: [
        { action: 'goto', path: '/', wait: 1600 },
        { action: 'scrollTo', selector: 'a[href="/assessment"]', zoom: Z.field, wait: 2600 },
        { action: 'zoomOut', wait: 800 },
      ],
    },
  ],
};
