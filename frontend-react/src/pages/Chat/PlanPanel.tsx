import { Icon } from '@/components/Icon/Icon';
import { Spinner } from '@/components/Spinner/Spinner';
import styles from './PlanPanel.module.css';

export interface PlanStep {
  title: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export interface PlanPanelProps {
  steps: PlanStep[];
  currentStep: number;
  onClose: () => void;
}

export function PlanPanel({ steps, currentStep, onClose }: PlanPanelProps) {
  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.headerTitle}>执行计划</span>
        <button className={styles.closeBtn} onClick={onClose} aria-label="关闭">
          <Icon name="close" size={14} />
        </button>
      </div>

      <ol className={styles.stepList}>
        {steps.map((step, i) => (
          <li
            key={i}
            className={[
              styles.step,
              i === currentStep ? styles.stepCurrent : '',
              step.status === 'completed' ? styles.stepCompleted : '',
              step.status === 'failed' ? styles.stepFailed : '',
            ].filter(Boolean).join(' ')}
          >
            <span className={styles.stepNumber}>{i + 1}</span>
            <span className={styles.stepTitle}>{step.title}</span>
            <span className={styles.stepStatus}>
              {step.status === 'running' && <Spinner size={14} />}
              {step.status === 'completed' && <Icon name="check" size={14} />}
              {step.status === 'failed' && <Icon name="alert" size={14} />}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
