export default function SiteRegistration() {
  const record = process.env.NEXT_PUBLIC_ICP_RECORD?.trim();
  if (!record) return null;
  return (
    <footer className="site-registration">
      <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">{record}</a>
    </footer>
  );
}
