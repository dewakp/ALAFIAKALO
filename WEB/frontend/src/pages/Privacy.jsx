import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';
import { t } from '../i18n';

/**
 * Public privacy policy. Also the Privacy Policy URL required by App Store
 * Connect and Google Play.
 *
 * Every statement here is meant to describe what the software actually does —
 * the collected-data list is the same one declared in the iOS privacy manifest
 * (IOS/ALAFIA/Resources/PrivacyInfo.xcprivacy), so the two cannot drift into
 * contradicting each other. If you change what the app collects, change both.
 */

const LAST_UPDATED = '13 August 2026';

const COLLECTED = [
  {
    icon: '❤️',
    get title() { return t('Privacy.health_and_fitness'); },
    get desc() { return t('Privacy.meals_nutrients_vitals_lab_results'); },
  },
  {
    icon: '👤',
    get title() { return t('Privacy.account_details'); },
    get desc() { return t('Privacy.your_name_email_address_phone_number_if'); },
  },
  {
    icon: '📷',
    get title() { return t('Privacy.photos_you_attach'); },
    get desc() { return t('Privacy.meal_photos_medication_labels_and_photos'); },
  },
  {
    icon: '📝',
    get title() { return t('Privacy.what_you_write'); },
    get desc() { return t('Privacy.journal_entries_notes_and_the_messages'); },
  },
];

const NEVER = [
  'We do not sell your data. Not to anyone, for any purpose.',
  'We do not use your data for advertising, and there are no advertising SDKs in our apps.',
  'We do not track you across other companies’ apps or websites. ALAFIA contains no tracking SDK and requests no advertising identifier.',
  'We do not use your health data to train third-party AI models.',
];

export default function Privacy() {
  return (
    <MarketingPage>
      <section className="section-wrap section-wrap--top section-wrap--narrow">
        <div className="section-head">
          <span className="eyebrow">YOUR DATA</span>
          <h2>{t('Privacy.privacy')}</h2>
          <p>
            {t('Privacy.alafia_holds_some_of_the_most_sensitive')}
          </p>
        </div>

        <p className="mk-cta-note">{t('Privacy.last_updated', { LAST_UPDATED })}</p>

        <h3>{t('Privacy.what_we_collect')}</h3>
        <p>
          {t('Privacy.only_what_the_app_needs_to_work')}
        </p>
        <div className="features-grid">
          {COLLECTED.map(c => (
            <div className="feat-card" key={c.title}>
              <span className="feat-icon">{c.icon}</span>
              <h3>{c.title}</h3>
              <p>{c.desc}</p>
            </div>
          ))}
        </div>

        <h3>{t('Privacy.what_we_never_do')}</h3>
        <ul className="mk-list">
          {NEVER.map(n => <li key={n}>{n}</li>)}
        </ul>

        <h3>{t('Privacy.where_your_data_goes')}</h3>
        <p>
          {t('Privacy.alafia_runs_on_google_cloud_in_the')}
        </p>
        <p>
          <strong>{t('Privacy.you_are_never_identified_to_an_ai')}</strong> {t('Privacy.alafia_s_ai_features_are_answered_by')}
          <code>alafia-ba9e8bb2f9077c6e</code>{t('Privacy.which_means_nothing_outside_alafia_and')}
        </p>
        <p>
          {t('Privacy.what_the_provider_receives_is_the_health')} <strong>{t('Privacy.your_data_is_never_used_to_train_anyone')}</strong> {t('Privacy.you_choose_whether_to_enable_ai_features')}
        </p>
        <p>
          {t('Privacy.a_small_number_of_service_providers')}
        </p>
        <ul className="mk-list">
          <li><strong>{t('Privacy.payments')}</strong> {t('Privacy.stripe_handles_web_subscriptions_and_the')}</li>
          <li><strong>{t('Privacy.email')}</strong> {t('Privacy.resend_delivers_account_email_such_as')}</li>
          <li><strong>{t('Privacy.nutrition_reference_data')}</strong> {t('Privacy.we_look_food_up_in_the_usda_fooddata')}</li>
        </ul>

        <h3>{t('Privacy.your_rights')}</h3>
        <p>
          {t('Privacy.wherever_you_live_you_can_exercise_all')}
        </p>
        <ul className="mk-list">
          <li><strong>{t('Privacy.see_it')}</strong> {t('Privacy.every_record_is_visible_in_the_app')}</li>
          <li><strong>{t('Privacy.export_it')}</strong> {t('Privacy.request_a_machine_readable_copy_of')}</li>
          <li><strong>{t('Privacy.correct_it')}</strong> {t('Privacy.edit_your_records_directly_with_a_few')}</li>
          <li><strong>{t('Privacy.delete_it')}</strong> {t('Privacy.request_deletion_of_your_account_and_its')}</li>
          <li><strong>{t('Privacy.withdraw_consent')}</strong> {t('Privacy.optional_data_uses_are_off_unless_you')}</li>
        </ul>
        <p>
          {t('Privacy.signed_in_these_live_under')} <strong>{t('Privacy.privacy_settings')}</strong>{t('Privacy.otherwise_email')}{' '}
          <a className="card-link" href="mailto:privacy@alafia.app">privacy@alafia.app</a> {t('Privacy.and_we_will_action_it')}
        </p>

        <h3>{t('Privacy.improving_alafia')}</h3>
        <p>
          {t('Privacy.a_meal_photo_you_take_is_kept_with_that')}
        </p>
        <p>
          {t('Privacy.using_those_photos_to')} <strong>{t('Privacy.train_a_shared_model')}</strong> {t('Privacy.is_a_separate_question_and_it_is')} <strong>{t('Privacy.off_by_default')}</strong>{t('Privacy.your_photos_and_corrections_only_help')}
        </p>

        <h3>{t('Privacy.children_and_families')}</h3>
        <p>
          {t('Privacy.alafia_has_no_age_limit_health_is_a')}
        </p>
        <p>
          {t('Privacy.an_account_for_a_child_should_be_created')}
        </p>

        <h3>{t('Privacy.how_long_we_keep_it')}</h3>
        <p>
          {t('Privacy.your_records_are_kept_while_your_account')}
        </p>

        <h3>{t('Privacy.changes')}</h3>
        <p>
          {t('Privacy.if_we_make_a_material_change_to_this')}
        </p>

        <div className="callout callout--danger">
          <strong>{t('Privacy.not_medical_advice_and_not_an_emergency')}</strong> {t('Privacy.alafia_helps_you_organise_and_understand')}
        </div>

        <div className="mk-cta">
          <p className="mk-cta-note">
            {t('Privacy.questions_about_any_of_this_go_to')}{' '}
            <a className="card-link" href="mailto:privacy@alafia.app">privacy@alafia.app</a>{t('Privacy.or_the_data_protection_officer_at')}{' '}
            <a className="card-link" href="mailto:dpo@alafia.app">dpo@alafia.app</a>{t('Privacy.other_enquiries_belong_on_the')} <Link to="/contact">{t('Privacy.contact')}</Link> {t('Privacy.page')}
          </p>
          <Link to="/contact" className="btn-primary-lg">{t('Privacy.contact_us')}</Link>
        </div>
      </section>
    </MarketingPage>
  );
}
