import type { Tour } from './src/types';

// The whole video is described here. Edit this file, run `npm run record`,
// then `npm run render`. Nothing about timing or zoom coordinates is set by
// hand: the recorder measures each element it interacts with and writes the
// camera moves and captions into public/tour/timeline.json.
//
// Scene order, on-screen text and narration follow the storyboard:
//   hook -> What's Stopping You -> Discover Your Idea -> Leap Calculator
//   -> Idea To Plan -> call to action. About 90 seconds.
//
// Selectors are Playwright selectors. `:visible` matters on the header
// because the desktop and mobile navs both exist in the DOM.

const NAV = (label: string) => `header >> :visible >> text="${label}"`;

export const tour: Tour = {
  baseUrl: process.env.BASE_URL ?? 'https://quityourlifeandtravel.com',
  viewport: { width: 1440, height: 900 },
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
        { action: 'zoom', selector: 'h1', level: 1.25, wait: 3200 },
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
        { action: 'click', selector: NAV("What's Stopping You"), zoom: 1.6, wait: 2200 },
        { action: 'zoom', selector: 'text=Question 1 of 16', level: 1.35, wait: 2400 },
        { action: 'click', selector: 'button:has-text("Four to nine months")', zoom: 1.5, wait: 1600 },
        { action: 'click', selector: 'button:has-text("Most of it, with some disruption")', zoom: 1.5, wait: 1600 },
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
        { action: 'click', selector: NAV('Discover Your Idea'), zoom: 1.6, wait: 2200 },
        { action: 'zoom', selector: '#discover-your-idea h2', level: 1.3, wait: 1800 },
        { action: 'click', selector: '#discover-your-idea a[href="/assessment"]', zoom: 1.5, wait: 2200 },
        { action: 'click', selector: 'button:has-text("Writing & copywriting")', zoom: 1.4, wait: 500 },
        { action: 'click', selector: 'button:has-text("AI & automation tools")', zoom: false, wait: 700 },
        { action: 'click', selector: 'button:has-text("Next")', zoom: false, wait: 1000 },
        { action: 'click', selector: 'button:has-text("Problem-solving")', zoom: 1.4, wait: 500 },
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
        { action: 'click', selector: NAV('Leap Calculator'), zoom: 1.6, wait: 2200 },
        { action: 'type', selector: 'input[placeholder="Spendable cash"]', text: '25000', zoom: 1.5, wait: 1400 },
        { action: 'scrollTo', selector: 'text=What Life in Chiang Mai Costs', zoom: 1.3, wait: 2400 },
        { action: 'scrollTo', selector: 'text=Net cash for your runway', zoom: 1.5, wait: 2600 },
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
        { action: 'click', selector: NAV('Idea To Plan'), zoom: 1.6, wait: 2200 },
        { action: 'zoom', selector: '#idea-to-plan h2', level: 1.3, wait: 3000 },
        { action: 'scrollTo', selector: 'text=Plans start at $25', zoom: 1.7, wait: 3200 },
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
        { action: 'zoom', selector: 'a[href="/assessment"]', level: 1.5, wait: 2600 },
        { action: 'zoomOut', wait: 800 },
      ],
    },
  ],
};
