import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} {...props}>
      {children}
    </svg>
  );
}

export function CalendarIcon(props: IconProps) {
  return <Icon {...props}><path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3.75 9h16.5M5.25 4.5h13.5a1.5 1.5 0 0 1 1.5 1.5v13.5H3.75V6a1.5 1.5 0 0 1 1.5-1.5Z" /></Icon>;
}

export function ArrowIcon(props: IconProps) {
  return <Icon {...props}><path strokeLinecap="round" strokeLinejoin="round" d="m9 18 6-6-6-6" /></Icon>;
}

export function PeopleIcon(props: IconProps) {
  return <Icon {...props}><path strokeLinecap="round" strokeLinejoin="round" d="M16 18.75a4 4 0 0 0-8 0M12 13.25a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM18 12.5a2.25 2.25 0 0 1 2.25 2.25M6 12.5a2.25 2.25 0 0 0-2.25 2.25" /></Icon>;
}

export function ClockIcon(props: IconProps) {
  return <Icon {...props}><circle cx="12" cy="12" r="8.25" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 7.5V12l3 1.75" /></Icon>;
}

export function CheckIcon(props: IconProps) {
  return <Icon {...props}><path strokeLinecap="round" strokeLinejoin="round" d="m6.75 12 3.5 3.5 7-7" /></Icon>;
}
