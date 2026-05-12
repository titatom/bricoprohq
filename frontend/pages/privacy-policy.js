import Head from 'next/head';
import Link from 'next/link';

export default function PrivacyPolicy() {
  return (
    <>
      <Head>
        <title>Privacy Policy – Bricopro HQ</title>
        <meta name="description" content="Privacy Policy for Bricopro HQ" />
      </Head>

      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-brand-600 text-white">
          <div className="max-w-4xl mx-auto px-6 py-6 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
              <img
                src="/logos/bricopro-mark.png"
                alt="Bricopro"
                className="h-8 w-8"
                onError={(e) => { e.currentTarget.src = '/logos/bricopro-mark.svg'; }}
              />
              <span className="font-bold text-lg tracking-tight">Bricopro HQ</span>
            </Link>
            <nav className="flex gap-4 text-sm">
              <Link href="/privacy-policy" className="underline underline-offset-2 opacity-90">Privacy Policy</Link>
              <Link href="/terms" className="hover:underline underline-offset-2 opacity-75 hover:opacity-90 transition-opacity">Terms &amp; Conditions</Link>
            </nav>
          </div>
        </header>

        {/* Content */}
        <main className="max-w-4xl mx-auto px-6 py-12">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 md:p-12">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Privacy Policy</h1>
            <p className="text-sm text-gray-500 mb-8">Last updated: May 2026</p>

            <div className="prose prose-gray max-w-none space-y-8 text-gray-700 leading-relaxed">

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">1. Introduction</h2>
                <p>
                  Bricopro HQ (&ldquo;we&rdquo;, &ldquo;our&rdquo;, or &ldquo;us&rdquo;) operates a business management platform designed for
                  home improvement and renovation professionals. This Privacy Policy explains how we collect,
                  use, disclose, and safeguard information when you use our platform, including through
                  integrations with third-party services such as Meta, Google, and Jobber.
                </p>
                <p className="mt-3">
                  By using Bricopro HQ, you agree to the practices described in this policy. If you do not
                  agree, please discontinue use of the platform.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">2. Information We Collect</h2>
                <p className="font-medium text-gray-800 mb-2">2.1 Information you provide directly</p>
                <ul className="list-disc pl-6 space-y-1">
                  <li>Account credentials (email address and password)</li>
                  <li>Business information and settings you configure within the platform</li>
                  <li>Campaign content, messages, and media you create or upload</li>
                </ul>

                <p className="font-medium text-gray-800 mt-4 mb-2">2.2 Information collected through integrations</p>
                <p>When you connect third-party services, we collect only the data necessary to operate the integration:</p>
                <ul className="list-disc pl-6 space-y-1 mt-2">
                  <li><strong>Meta (Facebook &amp; Instagram):</strong> Page access tokens, page metadata, and publishing permissions required to schedule and post content on your behalf.</li>
                  <li><strong>Google Calendar:</strong> OAuth access tokens to read and write calendar events on your behalf.</li>
                  <li><strong>Google Business Profile:</strong> OAuth access tokens to manage your business listing.</li>
                  <li><strong>Jobber:</strong> OAuth access tokens and job/client data required for dashboard and KPI features.</li>
                </ul>

                <p className="font-medium text-gray-800 mt-4 mb-2">2.3 Usage and technical data</p>
                <ul className="list-disc pl-6 space-y-1">
                  <li>Log data (IP address, browser type, pages visited, timestamps)</li>
                  <li>Error and diagnostic information to maintain platform reliability</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">3. How We Use Your Information</h2>
                <p>We use collected information to:</p>
                <ul className="list-disc pl-6 space-y-1 mt-2">
                  <li>Provide, operate, and maintain the Bricopro HQ platform</li>
                  <li>Execute actions on connected platforms on your behalf (e.g. publishing posts, syncing calendar events)</li>
                  <li>Authenticate you and secure your account</li>
                  <li>Display KPIs, analytics, and campaign performance data</li>
                  <li>Send transactional notifications related to your account</li>
                  <li>Diagnose bugs and improve platform performance</li>
                </ul>
                <p className="mt-3">
                  We do <strong>not</strong> sell your personal data to third parties, and we do not use your data
                  to train machine learning or AI models.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">4. Data Sharing and Disclosure</h2>
                <p>We may share information only in the following circumstances:</p>
                <ul className="list-disc pl-6 space-y-1 mt-2">
                  <li><strong>Third-party integrations:</strong> Data is transmitted to connected services (Meta, Google, Jobber) solely to carry out actions you have requested.</li>
                  <li><strong>Service providers:</strong> Hosting and infrastructure providers who process data on our behalf under confidentiality obligations.</li>
                  <li><strong>Legal requirements:</strong> If required by law, court order, or to protect the rights and safety of our users.</li>
                  <li><strong>Business transfers:</strong> In the event of a merger, acquisition, or sale of assets, with appropriate notice to you.</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">5. Data Retention</h2>
                <p>
                  We retain your data for as long as your account is active or as needed to provide services.
                  OAuth tokens for connected integrations are stored only as long as the integration remains
                  active. You may revoke access to any integration at any time from the Settings page,
                  which removes the associated tokens from our system. Upon account deletion, we remove
                  your personal data within 30 days, except where retention is required by law.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">6. Security</h2>
                <p>
                  We implement industry-standard security measures including encrypted storage of credentials,
                  HTTPS for all data in transit, and token-based authentication. However, no system is
                  completely secure, and we encourage you to use a strong, unique password for your account.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">7. Your Rights</h2>
                <p>Depending on your location, you may have the right to:</p>
                <ul className="list-disc pl-6 space-y-1 mt-2">
                  <li>Access the personal data we hold about you</li>
                  <li>Request correction of inaccurate data</li>
                  <li>Request deletion of your personal data</li>
                  <li>Withdraw consent for integrations at any time</li>
                  <li>Lodge a complaint with your local data protection authority</li>
                </ul>
                <p className="mt-3">To exercise these rights, contact us at the address in Section 9.</p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">8. Third-Party Services</h2>
                <p>
                  Bricopro HQ integrates with third-party platforms whose own privacy policies govern the
                  data they collect. We encourage you to review the privacy policies of Meta, Google, and
                  Jobber when using those integrations. We are not responsible for the privacy practices of
                  third-party services.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">9. Contact Us</h2>
                <p>
                  If you have questions or concerns about this Privacy Policy or our data practices, please
                  contact us:
                </p>
                <div className="mt-3 p-4 bg-gray-50 rounded-lg border border-gray-200 text-sm">
                  <p className="font-medium text-gray-800">Bricopro HQ</p>
                  <p className="text-gray-600 mt-1">Email: <a href="mailto:privacy@bricoprohq.com" className="text-brand-600 hover:underline">privacy@bricoprohq.com</a></p>
                </div>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">10. Changes to This Policy</h2>
                <p>
                  We may update this Privacy Policy from time to time. Changes will be posted on this page
                  with an updated date. Continued use of the platform after changes are posted constitutes
                  acceptance of the revised policy.
                </p>
              </section>
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer className="max-w-4xl mx-auto px-6 py-8 text-center text-sm text-gray-400">
          <p>
            &copy; {new Date().getFullYear()} Bricopro HQ &mdash;{' '}
            <Link href="/privacy-policy" className="hover:text-gray-600 transition-colors">Privacy Policy</Link>
            {' '}&middot;{' '}
            <Link href="/terms" className="hover:text-gray-600 transition-colors">Terms &amp; Conditions</Link>
          </p>
        </footer>
      </div>
    </>
  );
}
